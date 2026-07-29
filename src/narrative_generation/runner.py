"""End-to-end independent narrative generation runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from narrative_generation.config import NarrativeGenerationConfig
from narrative_generation.generator import (
    NarrativeUnitGenerator,
    UnitGenerationResult,
)
from narrative_generation.inputs import (
    LoadedNarrativeInputs,
    load_and_merge_inputs,
)
from narrative_generation.model_adapter import TextGenerator
from narrative_generation.text import (
    PLACEHOLDER_PATTERNS,
    normalize_text,
)
from narrative_generation.units import (
    build_narrative_units,
    resolved_structural_operation_numbers,
)


@dataclass(frozen=True, slots=True)
class NarrativeRunResult:
    generated_narrative_path: Path
    draft_path: Path
    validation_report_path: Path
    preview_path: Path
    generated_narrative: dict
    validation_report: dict


def _write_json(
    path: Path,
    payload: dict,
) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_narrative_generation(
    *,
    narrative_plan_path: Path,
    operation_contexts_path: Path,
    output_dir: Path,
    text_generator: TextGenerator | None = None,
    config: NarrativeGenerationConfig | None = None,
) -> NarrativeRunResult:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if config is None:
        config = NarrativeGenerationConfig(
            use_model=text_generator is not None,
            cache_dir=output_dir / "narrative_cache",
        )
    elif config.cache_dir is None:
        config = NarrativeGenerationConfig(
            model_name=config.model_name,
            prompt_version=config.prompt_version,
            max_attempts_per_unit=(
                config.max_attempts_per_unit
            ),
            max_new_tokens_per_unit=(
                config.max_new_tokens_per_unit
            ),
            use_model=config.use_model,
            cache_dir=output_dir / "narrative_cache",
        )

    loaded: LoadedNarrativeInputs = (
        load_and_merge_inputs(
            narrative_plan_path=narrative_plan_path,
            operation_contexts_path=(
                operation_contexts_path
            ),
        )
    )
    plan = loaded.narrative_plan

    units, coverage_summary, build_warnings = (
        build_narrative_units(plan)
    )

    generated_narrative_path = (
        output_dir / "generated_narrative.json"
    )
    draft_path = output_dir / "narrative_draft.json"
    validation_report_path = (
        output_dir / "narrative_validation_report.json"
    )
    preview_path = output_dir / "narrative_preview.txt"

    draft_output = {
        "process_id": plan["process_id"],
        "process_title": plan["process_title"],
        "input_files": {
            "narrative_plan": str(
                loaded.narrative_plan_path
            ),
            "operation_contexts": str(
                loaded.operation_contexts_path
            ),
        },
        "units": units,
        "coverage_summary": coverage_summary,
        "merge_warnings": loaded.merge_warnings,
        "build_warnings": build_warnings,
    }
    _write_json(draft_path, draft_output)

    unit_generator = NarrativeUnitGenerator(
        process_title=plan["process_title"],
        config=config,
        text_generator=text_generator,
    )

    results: list[UnitGenerationResult] = [
        unit_generator.generate(unit)
        for unit in units
    ]

    paragraphs = [
        " ".join(result.paragraph.split()).strip()
        for result in results
    ]

    if any(not paragraph for paragraph in paragraphs):
        raise RuntimeError(
            "At least one final narrative paragraph is empty."
        )

    placeholder_count = sum(
        any(
            normalize_text(pattern)
            in normalize_text(paragraph)
            for pattern in PLACEHOLDER_PATTERNS
        )
        for paragraph in paragraphs
    )

    if placeholder_count:
        raise RuntimeError(
            f"{placeholder_count} placeholder(s) detected."
        )

    fallback_units = [
        result.unit_id
        for result in results
        if result.fallback_used
    ]
    cached_units = [
        result.unit_id
        for result in results
        if result.cache_used
    ]

    resolved_structural_numbers = (
        resolved_structural_operation_numbers(plan)
    )
    ambiguous_operations = sorted(
        int(operation["number"])
        for operation in plan["operations"]
        if (
            operation.get("order_ambiguous")
            and int(operation["number"])
            not in resolved_structural_numbers
        )
    )

    manual_review_required = bool(
        fallback_units
        or loaded.merge_warnings
        or build_warnings
        or ambiguous_operations
    )

    validation_report = {
        "process_id": plan["process_id"],
        "process_title": plan["process_title"],
        "model_name": (
            config.model_name
            if config.use_model
            else "deterministic"
        ),
        "prompt_version": config.prompt_version,
        "generation_strategy": (
            "deterministic_bpmn_plan_"
            "with_independent_qwen_rewriting"
        ),
        "coverage_summary": coverage_summary,
        "unit_count": len(units),
        "paragraph_count": len(paragraphs),
        "fallback_units": fallback_units,
        "cached_units": cached_units,
        "placeholder_count": placeholder_count,
        "paragraph_lengths": [
            len(paragraph)
            for paragraph in paragraphs
        ],
        "merge_warnings": loaded.merge_warnings,
        "build_warnings": build_warnings,
        "ambiguous_operations": ambiguous_operations,
        "manual_review_required": (
            manual_review_required
        ),
        "unit_results": [
            {
                "unit_id": result.unit_id,
                "attempts": result.attempts,
                "fallback_used": (
                    result.fallback_used
                ),
                "cache_used": result.cache_used,
                "last_error": result.last_error,
            }
            for result in results
        ],
    }

    generated_narrative = {
        "process_id": plan["process_id"],
        "process_title": plan["process_title"],
        "model_name": (
            config.model_name
            if config.use_model
            else "deterministic"
        ),
        "paragraphs": paragraphs,
        "quality_summary": {
            "paragraph_count": len(paragraphs),
            "placeholder_count": placeholder_count,
            "max_paragraph_characters": max(
                len(paragraph)
                for paragraph in paragraphs
            ),
        },
    }

    _write_json(
        generated_narrative_path,
        generated_narrative,
    )
    _write_json(
        validation_report_path,
        validation_report,
    )

    preview_lines = [
        plan["process_title"],
        "=" * len(plan["process_title"]),
        "",
    ]

    for index, paragraph in enumerate(
        paragraphs,
        start=1,
    ):
        preview_lines.extend(
            [
                f"Paragraphe {index}",
                paragraph,
                "",
            ]
        )

    preview_path.write_text(
        "\n".join(preview_lines),
        encoding="utf-8",
    )

    return NarrativeRunResult(
        generated_narrative_path=(
            generated_narrative_path
        ),
        draft_path=draft_path,
        validation_report_path=(
            validation_report_path
        ),
        preview_path=preview_path,
        generated_narrative=generated_narrative,
        validation_report=validation_report,
    )
