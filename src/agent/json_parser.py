"""Safe parsing and validation of structured LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from .models import GeneratedOperationContent


class LlmOutputError(ValueError):
    """Raised when the model response cannot be validated."""


_CODE_FENCE_PATTERN = re.compile(
    r"```(?:json)?\s*(.*?)\s*```",
    flags=re.DOTALL | re.IGNORECASE,
)


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract one JSON object from an LLM response."""

    cleaned = text.strip()

    fenced_match = _CODE_FENCE_PATTERN.search(cleaned)
    if fenced_match:
        cleaned = fenced_match.group(1).strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise LlmOutputError(
                "The model response does not contain a JSON object."
            )

        candidate = cleaned[start : end + 1]

        try:
            result = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise LlmOutputError(
                f"Invalid JSON returned by the model: {exc}"
            ) from exc

    if not isinstance(result, dict):
        raise LlmOutputError(
            "The model response must be a JSON object."
        )

    return result


def parse_generated_content(
    text: str,
) -> GeneratedOperationContent:
    """Extract and validate generated operation content."""

    raw_data = extract_json_object(text)

    try:
        return GeneratedOperationContent.model_validate(
            raw_data
        )
    except ValidationError as exc:
        raise LlmOutputError(
            f"The JSON does not match the expected schema: {exc}"
        ) from exc
