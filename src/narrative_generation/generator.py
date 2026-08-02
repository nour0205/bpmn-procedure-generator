"""Generate, validate and cache narrative units."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from narrative_generation.config import NarrativeGenerationConfig
from narrative_generation.model_adapter import (
    TextGenerator,
    extract_json_object,
)
from narrative_generation.models import GeneratedUnit
from narrative_generation.prompts import (
    SYSTEM_PROMPT,
    build_unit_prompt,
)
from narrative_generation.text import stable_hash
from narrative_generation.validation import (
    assemble_paragraph,
    validate_generated_unit,
)


@dataclass(frozen=True, slots=True)
class UnitGenerationResult:
    unit_id: str
    sentences: list[str]
    paragraph: str
    attempts: int
    fallback_used: bool
    cache_used: bool
    last_error: str | None


class NarrativeUnitGenerator:
    def __init__(
        self,
        *,
        process_title: str,
        config: NarrativeGenerationConfig,
        text_generator: TextGenerator | None,
    ) -> None:
        self.process_title = process_title
        self.config = config
        self.text_generator = text_generator

        if self.config.use_model and self.text_generator is None:
            raise ValueError(
                "A text_generator is required when use_model=True."
            )

        if self.config.cache_dir is not None:
            self.config.cache_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

    @staticmethod
    def deterministic_sentences(
        unit: dict,
    ) -> list[str]:
        return [
            fact["text"]
            for fact in unit["facts"]
        ]

    def _cache_path(
        self,
        unit: dict,
    ) -> Path | None:
        if self.config.cache_dir is None:
            return None

        signature = stable_hash(
            {
                "model_name": self.config.model_name,
                "prompt_version": (
                    self.config.prompt_version
                ),
                "unit": unit,
            }
        )

        return (
            self.config.cache_dir
            / f"{unit['unit_id']}_{signature[:16]}.json"
        )

    def _load_cache(
        self,
        unit: dict,
    ) -> list[str] | None:
        path = self._cache_path(unit)

        if path is None or not path.exists():
            return None

        try:
            payload = json.loads(
                path.read_text(encoding="utf-8")
            )
            generated = GeneratedUnit.model_validate(
                payload["generated"]
            )
            return validate_generated_unit(
                unit,
                generated,
            )
        except Exception:
            path.unlink(missing_ok=True)
            return None

    def _save_cache(
        self,
        unit: dict,
        generated: GeneratedUnit,
    ) -> None:
        path = self._cache_path(unit)

        if path is None:
            return

        path.write_text(
            json.dumps(
                {
                    "unit_id": unit["unit_id"],
                    "model_name": (
                        self.config.model_name
                    ),
                    "prompt_version": (
                        self.config.prompt_version
                    ),
                    "generated": generated.model_dump(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def generate(
        self,
        unit: dict,
    ) -> UnitGenerationResult:
        if all(fact["locked"] for fact in unit["facts"]):
            deterministic = self.deterministic_sentences(unit)

            return UnitGenerationResult(
                unit_id=unit["unit_id"],
                sentences=deterministic,
                paragraph=assemble_paragraph(
                    unit,
                    deterministic,
                ),
                attempts=0,
                fallback_used=False,
                cache_used=False,
                last_error=None,
            )

        cached = self._load_cache(unit)

        if cached is not None:
            return UnitGenerationResult(
                unit_id=unit["unit_id"],
                sentences=cached,
                paragraph=assemble_paragraph(
                    unit,
                    cached,
                ),
                attempts=0,
                fallback_used=False,
                cache_used=True,
                last_error=None,
            )

        if not self.config.use_model:
            fallback = self.deterministic_sentences(unit)

            return UnitGenerationResult(
                unit_id=unit["unit_id"],
                sentences=fallback,
                paragraph=assemble_paragraph(
                    unit,
                    fallback,
                ),
                attempts=0,
                fallback_used=True,
                cache_used=False,
                last_error="use_model=False",
            )

        assert self.text_generator is not None
        last_error: str | None = None

        for attempt in range(
            1,
            self.config.max_attempts_per_unit + 1,
        ):
            try:
                raw_response = self.text_generator.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=build_unit_prompt(
                        process_title=self.process_title,
                        unit=unit,
                        validation_error=last_error,
                    ),
                    max_new_tokens=min(
                        self.config.max_new_tokens_per_unit,
                        160
                        + 130
                        * sum(
                            not fact["locked"]
                            for fact in unit["facts"]
                        ),
                    ),
                )
                generated = GeneratedUnit.model_validate(
                    extract_json_object(raw_response)
                )
                sentences = validate_generated_unit(
                    unit,
                    generated,
                )
                self._save_cache(unit, generated)

                return UnitGenerationResult(
                    unit_id=unit["unit_id"],
                    sentences=sentences,
                    paragraph=assemble_paragraph(
                        unit,
                        sentences,
                    ),
                    attempts=attempt,
                    fallback_used=False,
                    cache_used=False,
                    last_error=None,
                )

            except Exception as error:
                last_error = str(error)

        fallback = self.deterministic_sentences(unit)

        return UnitGenerationResult(
            unit_id=unit["unit_id"],
            sentences=fallback,
            paragraph=assemble_paragraph(
                unit,
                fallback,
            ),
            attempts=(
                self.config.max_attempts_per_unit
            ),
            fallback_used=True,
            cache_used=False,
            last_error=last_error,
        )
