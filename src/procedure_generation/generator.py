"""Generate one procedure operation with validation and caching."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from procedure_generation.config import (
    ProcedureGenerationConfig,
)
from procedure_generation.model_adapter import (
    TextGenerator,
    extract_json_object,
)
from procedure_generation.models import (
    GeneratedOperationContent,
)
from procedure_generation.prompts import (
    SYSTEM_PROMPT,
    build_operation_prompt,
)
from procedure_generation.text import stable_hash
from procedure_generation.validation import (
    build_operation_output,
    deterministic_description,
    validate_generated_content,
)


@dataclass(frozen=True, slots=True)
class OperationGenerationResult:
    operation_number: int
    operation: dict
    attempts: int
    fallback_used: bool
    cache_used: bool
    model_used: bool
    last_error: str | None


class ProcedureOperationGenerator:
    def __init__(
        self,
        *,
        config: ProcedureGenerationConfig,
        text_generator: TextGenerator | None,
    ) -> None:
        self.config = config
        self.text_generator = text_generator

        if (
            self.config.use_model
            and self.text_generator is None
        ):
            raise ValueError(
                "A text_generator is required "
                "when use_model=True."
            )

        if self.config.cache_dir is not None:
            self.config.cache_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

    def _cache_path(
        self,
        context: dict,
    ) -> Path | None:
        if self.config.cache_dir is None:
            return None

        signature = stable_hash(
            {
                "model_name": (
                    self.config.model_name
                ),
                "prompt_version": (
                    self.config.prompt_version
                ),
                "context": context,
            }
        )

        return (
            self.config.cache_dir
            / (
                f"operation_"
                f"{context['operation_number']}_"
                f"{signature[:16]}.json"
            )
        )

    def _load_cache(
        self,
        context: dict,
    ) -> tuple[
        str,
        list[str],
        list[str],
    ] | None:
        path = self._cache_path(
            context
        )

        if (
            path is None
            or not path.exists()
        ):
            return None

        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
            generated = (
                GeneratedOperationContent
                .model_validate(
                    payload["generated"]
                )
            )

            return validate_generated_content(
                context=context,
                generated=generated,
            )
        except Exception:
            path.unlink(
                missing_ok=True
            )
            return None

    def _save_cache(
        self,
        *,
        context: dict,
        generated: GeneratedOperationContent,
    ) -> None:
        path = self._cache_path(
            context
        )

        if path is None:
            return

        path.write_text(
            json.dumps(
                {
                    "operation_number": (
                        context[
                            "operation_number"
                        ]
                    ),
                    "model_name": (
                        self.config.model_name
                    ),
                    "prompt_version": (
                        self.config.prompt_version
                    ),
                    "generated": (
                        generated.model_dump()
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def generate(
        self,
        context: dict,
    ) -> OperationGenerationResult:
        (
            fallback_description,
            fallback_note_ids,
        ) = deterministic_description(
            context
        )

        execution_mode = str(
            context.get(
                "execution_mode",
                "",
            )
        ).casefold()

        # Events are rendered deterministically because their exact semantics
        # (especially J+X/J+Y markers) should never be reinterpreted.
        if execution_mode == "event":
            operation = build_operation_output(
                context=context,
                description=(
                    fallback_description
                ),
                incorporated_note_ids=(
                    fallback_note_ids
                ),
                missing_note_ids=[],
                fallback_used=False,
                last_error=None,
            )

            return OperationGenerationResult(
                operation_number=(
                    context[
                        "operation_number"
                    ]
                ),
                operation=operation,
                attempts=0,
                fallback_used=False,
                cache_used=False,
                model_used=False,
                last_error=None,
            )

        cached = self._load_cache(
            context
        )

        if cached is not None:
            (
                description,
                incorporated_ids,
                missing_ids,
            ) = cached

            operation = build_operation_output(
                context=context,
                description=description,
                incorporated_note_ids=(
                    incorporated_ids
                ),
                missing_note_ids=missing_ids,
                fallback_used=False,
                last_error=None,
            )

            return OperationGenerationResult(
                operation_number=(
                    context[
                        "operation_number"
                    ]
                ),
                operation=operation,
                attempts=0,
                fallback_used=False,
                cache_used=True,
                model_used=True,
                last_error=None,
            )

        if not self.config.use_model:
            operation = build_operation_output(
                context=context,
                description=(
                    fallback_description
                ),
                incorporated_note_ids=(
                    fallback_note_ids
                ),
                missing_note_ids=[],
                fallback_used=True,
                last_error=(
                    "Model use is disabled."
                ),
            )

            return OperationGenerationResult(
                operation_number=(
                    context[
                        "operation_number"
                    ]
                ),
                operation=operation,
                attempts=0,
                fallback_used=True,
                cache_used=False,
                model_used=False,
                last_error=(
                    "Model use is disabled."
                ),
            )

        last_error: str | None = None

        for attempt in range(
            1,
            self.config
            .max_attempts_per_operation
            + 1,
        ):
            try:
                raw_response = (
                    self.text_generator.generate(
                        system_prompt=SYSTEM_PROMPT,
                        user_prompt=(
                            build_operation_prompt(
                                context=context,
                                deterministic_fallback=(
                                    fallback_description
                                ),
                                validation_error=(
                                    last_error
                                ),
                            )
                        ),
                        max_new_tokens=(
                            self.config
                            .max_new_tokens_per_operation
                        ),
                    )
                )

                generated = (
                    GeneratedOperationContent
                    .model_validate(
                        extract_json_object(
                            raw_response
                        )
                    )
                )

                (
                    description,
                    incorporated_ids,
                    missing_ids,
                ) = validate_generated_content(
                    context=context,
                    generated=generated,
                )

                self._save_cache(
                    context=context,
                    generated=generated,
                )

                operation = build_operation_output(
                    context=context,
                    description=description,
                    incorporated_note_ids=(
                        incorporated_ids
                    ),
                    missing_note_ids=(
                        missing_ids
                    ),
                    fallback_used=False,
                    last_error=None,
                )

                return OperationGenerationResult(
                    operation_number=(
                        context[
                            "operation_number"
                        ]
                    ),
                    operation=operation,
                    attempts=attempt,
                    fallback_used=False,
                    cache_used=False,
                    model_used=True,
                    last_error=None,
                )

            except (
                ValueError,
                ValidationError,
                json.JSONDecodeError,
            ) as error:
                last_error = str(error)

        operation = build_operation_output(
            context=context,
            description=(
                fallback_description
            ),
            incorporated_note_ids=(
                fallback_note_ids
            ),
            missing_note_ids=[],
            fallback_used=True,
            last_error=last_error,
        )

        return OperationGenerationResult(
            operation_number=(
                context[
                    "operation_number"
                ]
            ),
            operation=operation,
            attempts=(
                self.config
                .max_attempts_per_operation
            ),
            fallback_used=True,
            cache_used=False,
            model_used=False,
            last_error=last_error,
        )
