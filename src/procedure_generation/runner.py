"""End-to-end independent procedure generation runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from procedure_generation.config import (
    ProcedureGenerationConfig,
)
from procedure_generation.generator import (
    OperationGenerationResult,
    ProcedureOperationGenerator,
)
from procedure_generation.inputs import (
    load_operation_contexts,
)
from procedure_generation.model_adapter import (
    TextGenerator,
)
from procedure_generation.models import (
    GeneratedProcedure,
)
from procedure_generation.text import (
    PLACEHOLDER_PATTERNS,
    normalize_text,
)
from procedure_generation.validation import (
    build_decisions,
    deterministic_description,
)


@dataclass(frozen=True, slots=True)
class ProcedureRunResult:
    generated_procedure_path: Path
    draft_path: Path
    validation_report_path: Path
    preview_path: Path
    generated_procedure: dict
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


def run_procedure_generation(
    *,
    operation_contexts_path: Path,
    output_dir: Path,
    text_generator: TextGenerator | None = None,
    config: (
        ProcedureGenerationConfig | None
    ) = None,
) -> ProcedureRunResult:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if config is None:
        config = ProcedureGenerationConfig(
            use_model=(
                text_generator is not None
            ),
            cache_dir=(
                output_dir
                / "procedure_cache"
            ),
        )
    elif config.cache_dir is None:
        config = ProcedureGenerationConfig(
            model_name=config.model_name,
            prompt_version=(
                config.prompt_version
            ),
            max_attempts_per_operation=(
                config
                .max_attempts_per_operation
            ),
            max_new_tokens_per_operation=(
                config
                .max_new_tokens_per_operation
            ),
            use_model=config.use_model,
            cache_dir=(
                output_dir
                / "procedure_cache"
            ),
            title_override=(
                config.title_override
            ),
        )

    loaded = load_operation_contexts(
        operation_contexts_path,
        title_override=(
            config.title_override
        ),
    )

    generated_procedure_path = (
        output_dir
        / "generated_procedure.json"
    )
    draft_path = (
        output_dir
        / "procedure_draft.json"
    )
    validation_report_path = (
        output_dir
        / "procedure_validation_report.json"
    )
    preview_path = (
        output_dir
        / "procedure_preview.txt"
    )

    draft = {
        "process_id": loaded.process_id,
        "title": loaded.title,
        "input_file": str(
            loaded.path
        ),
        "operations": [
            {
                "operation_number": (
                    context[
                        "operation_number"
                    ]
                ),
                "bpmn_element_id": (
                    context[
                        "bpmn_element_id"
                    ]
                ),
                "raw_name": (
                    context[
                        "raw_name"
                    ]
                ),
                "execution_mode": (
                    context[
                        "execution_mode"
                    ]
                ),
                "deterministic_description": (
                    deterministic_description(
                        context
                    )[0]
                ),
            }
            for context in loaded.contexts
        ],
        "input_warnings": (
            loaded.warnings
        ),
    }
    _write_json(
        draft_path,
        draft,
    )

    operation_generator = (
        ProcedureOperationGenerator(
            config=config,
            text_generator=(
                text_generator
            ),
        )
    )

    results: list[
        OperationGenerationResult
    ] = []

    for index, context in enumerate(
        loaded.contexts,
        start=1,
    ):
        print(
            f"[{index}/{len(loaded.contexts)}] "
            f"Operation {context['operation_number']}: "
            f"{context['raw_name']}"
        )
        results.append(
            operation_generator.generate(
                context
            )
        )

    operations = [
        result.operation
        for result in results
    ]
    decisions = build_decisions(
        loaded.contexts
    )

    placeholder_count = sum(
        any(
            normalize_text(pattern)
            in normalize_text(
                operation[
                    "description"
                ]
            )
            for pattern
            in PLACEHOLDER_PATTERNS
        )
        for operation in operations
    )

    if placeholder_count:
        raise RuntimeError(
            f"{placeholder_count} placeholder(s) "
            "were detected."
        )

    operation_numbers = [
        operation[
            "operation_number"
        ]
        for operation in operations
    ]

    if len(operation_numbers) != len(
        set(operation_numbers)
    ):
        raise RuntimeError(
            "Duplicate operation numbers "
            "were generated."
        )

    expected_numbers = {
        context[
            "operation_number"
        ]
        for context in loaded.contexts
    }
    actual_numbers = set(
        operation_numbers
    )

    missing_numbers = sorted(
        expected_numbers
        - actual_numbers
    )
    unknown_numbers = sorted(
        actual_numbers
        - expected_numbers
    )

    if (
        missing_numbers
        or unknown_numbers
    ):
        raise RuntimeError(
            "Generated operation coverage is invalid. "
            f"missing={missing_numbers}; "
            f"unknown={unknown_numbers}."
        )

    fallback_operations = [
        result.operation_number
        for result in results
        if result.fallback_used
    ]
    cached_operations = [
        result.operation_number
        for result in results
        if result.cache_used
    ]
    deterministic_event_operations = [
        result.operation_number
        for result in results
        if (
            not result.model_used
            and not result.fallback_used
        )
    ]
    operations_requiring_validation = [
        operation[
            "operation_number"
        ]
        for operation in operations
        if operation[
            "requires_validation"
        ]
    ]
    missing_note_count = sum(
        len(
            operation[
                "missing_note_ids"
            ]
        )
        for operation in operations
    )

    generation_warnings = [
        (
            "A deterministic fallback was used "
            f"for operation {number}."
        )
        for number in fallback_operations
    ]

    generated_payload = {
        "process_id": loaded.process_id,
        "title": loaded.title,
        "operation_count": len(
            operations
        ),
        "decisions": decisions,
        "operations": operations,
        "generation_warnings": (
            generation_warnings
        ),
        "quality_summary": {
            "operations_requiring_validation": (
                operations_requiring_validation
            ),
            "placeholder_count": (
                placeholder_count
            ),
            "missing_note_count": (
                missing_note_count
            ),
        },
    }

    generated_model = GeneratedProcedure.model_validate(
        generated_payload
    )
    generated_procedure = (
        generated_model.model_dump(
            mode="json",
            exclude_none=True,
        )
    )

    manual_review_required = bool(
        operations_requiring_validation
        or loaded.warnings
    )

    validation_report = {
        "process_id": loaded.process_id,
        "title": loaded.title,
        "model_name": (
            config.model_name
            if config.use_model
            else "deterministic"
        ),
        "prompt_version": (
            config.prompt_version
        ),
        "generation_strategy": (
            "deterministic_operation_contexts_"
            "with_validated_qwen_rewriting"
        ),
        "operation_count": len(
            operations
        ),
        "expected_operation_numbers": (
            sorted(
                expected_numbers
            )
        ),
        "generated_operation_numbers": (
            sorted(
                actual_numbers
            )
        ),
        "missing_operation_numbers": (
            missing_numbers
        ),
        "unknown_operation_numbers": (
            unknown_numbers
        ),
        "decision_count": len(
            decisions
        ),
        "fallback_operations": (
            fallback_operations
        ),
        "cached_operations": (
            cached_operations
        ),
        "deterministic_event_operations": (
            deterministic_event_operations
        ),
        "operations_requiring_validation": (
            operations_requiring_validation
        ),
        "placeholder_count": (
            placeholder_count
        ),
        "missing_note_count": (
            missing_note_count
        ),
        "input_warnings": (
            loaded.warnings
        ),
        "manual_review_required": (
            manual_review_required
        ),
        "operation_results": [
            {
                "operation_number": (
                    result.operation_number
                ),
                "attempts": (
                    result.attempts
                ),
                "fallback_used": (
                    result.fallback_used
                ),
                "cache_used": (
                    result.cache_used
                ),
                "model_used": (
                    result.model_used
                ),
                "last_error": (
                    result.last_error
                ),
            }
            for result in results
        ],
    }

    _write_json(
        generated_procedure_path,
        generated_procedure,
    )
    _write_json(
        validation_report_path,
        validation_report,
    )

    preview_lines = [
        loaded.title,
        "=" * len(
            loaded.title
        ),
        "",
    ]

    for operation in operations:
        preview_lines.extend(
            [
                (
                    f"{operation['operation_number']}. "
                    f"{operation['description']}"
                ),
                (
                    "Confiance : "
                    f"{operation['confidence']} | "
                    "Validation : "
                    f"{operation['requires_validation']}"
                ),
                "",
            ]
        )

    preview_path.write_text(
        "\n".join(
            preview_lines
        ),
        encoding="utf-8",
    )

    return ProcedureRunResult(
        generated_procedure_path=(
            generated_procedure_path
        ),
        draft_path=draft_path,
        validation_report_path=(
            validation_report_path
        ),
        preview_path=preview_path,
        generated_procedure=(
            generated_procedure
        ),
        validation_report=(
            validation_report
        ),
    )
