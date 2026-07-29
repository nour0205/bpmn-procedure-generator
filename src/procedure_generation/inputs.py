"""Load and normalize deterministic operation contexts."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from procedure_generation.text import looks_like_technical_title


@dataclass(frozen=True, slots=True)
class LoadedProcedureInput:
    path: Path
    process_id: str
    title: str
    contexts: list[dict]
    warnings: list[str]


def derive_execution_mode(context: dict) -> str:
    existing = str(
        context.get("execution_mode", "")
    ).strip()

    if existing:
        return existing

    source_type = str(
        context.get("source_type", "")
    ).casefold()

    element_kind = str(
        context.get("element_kind", "")
    ).casefold()

    if (
        source_type.endswith("event")
        or element_kind in {
            "event",
            "business_event",
        }
    ):
        return "event"

    if source_type == "servicetask":
        return "automated"

    if source_type in {
        "usertask",
        "manualtask",
    }:
        return "human"

    if (
        source_type
        in {
            "callactivity",
            "subprocess",
        }
        or element_kind == "subprocess"
    ):
        return "subprocess"

    return "unknown"


def _validate_reference(
    reference: dict,
    *,
    field_name: str,
    operation_number: int,
) -> dict:
    if not isinstance(reference, dict):
        raise TypeError(
            f"{field_name} for operation {operation_number} "
            "must contain objects."
        )

    required = {
        "id",
        "name",
        "element_kind",
    }
    missing = required - reference.keys()

    if missing:
        raise ValueError(
            f"{field_name} for operation {operation_number} "
            "is missing: "
            + ", ".join(sorted(missing))
        )

    return {
        "id": str(reference["id"]),
        "name": str(reference["name"]),
        "actor_name": (
            str(reference["actor_name"])
            if reference.get("actor_name") is not None
            else None
        ),
        "element_kind": str(
            reference["element_kind"]
        ),
    }


def _normalize_notes(
    notes: list,
    *,
    operation_number: int,
) -> list[dict]:
    result: list[dict] = []

    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise TypeError(
                f"Note {index + 1} for operation "
                f"{operation_number} must be an object "
                "with id and text."
            )

        note_id = str(note.get("id", "")).strip()
        text = str(note.get("text", "")).strip()

        if not note_id or not text:
            raise ValueError(
                f"Note {index + 1} for operation "
                f"{operation_number} must contain "
                "non-empty id and text."
            )

        result.append(
            {
                "id": note_id,
                "text": text,
            }
        )

    note_ids = [
        note["id"]
        for note in result
    ]

    if len(note_ids) != len(set(note_ids)):
        raise ValueError(
            f"Duplicate note IDs for operation "
            f"{operation_number}."
        )

    return result


def _normalize_branches(
    branches: list,
    *,
    operation_number: int,
) -> list[dict]:
    result: list[dict] = []

    for index, branch in enumerate(branches):
        if not isinstance(branch, dict):
            raise TypeError(
                f"Branch {index + 1} for operation "
                f"{operation_number} must be an object."
            )

        required = {
            "gateway_id",
            "target_element_id",
        }
        missing = required - branch.keys()

        if missing:
            raise ValueError(
                f"Branch {index + 1} for operation "
                f"{operation_number} is missing: "
                + ", ".join(sorted(missing))
            )

        result.append(
            {
                "gateway_id": str(
                    branch["gateway_id"]
                ),
                "gateway_name": (
                    str(branch["gateway_name"])
                    if branch.get("gateway_name")
                    is not None
                    else None
                ),
                "label": (
                    str(branch["label"])
                    if branch.get("label")
                    is not None
                    else None
                ),
                "condition": (
                    str(branch["condition"])
                    if branch.get("condition")
                    is not None
                    else None
                ),
                "is_default": bool(
                    branch.get(
                        "is_default",
                        False,
                    )
                ),
                "target_element_id": str(
                    branch["target_element_id"]
                ),
                "target_name": (
                    str(branch["target_name"])
                    if branch.get("target_name")
                    is not None
                    else None
                ),
            }
        )

    return result


def normalize_context(context: dict) -> dict:
    if not isinstance(context, dict):
        raise TypeError(
            "Each operation context must be an object."
        )

    required = {
        "operation_number",
        "bpmn_element_id",
        "raw_name",
        "element_kind",
        "source_type",
    }
    missing = required - context.keys()

    if missing:
        raise ValueError(
            "An operation context is missing: "
            + ", ".join(sorted(missing))
        )

    operation_number = int(
        context["operation_number"]
    )

    normalized = copy.deepcopy(context)
    normalized["operation_number"] = operation_number
    normalized["bpmn_element_id"] = str(
        context["bpmn_element_id"]
    )
    normalized["raw_name"] = str(
        context["raw_name"]
    ).strip()
    normalized["actor_name"] = (
        str(context["actor_name"]).strip()
        if context.get("actor_name") is not None
        else None
    )
    normalized["element_kind"] = str(
        context["element_kind"]
    )
    normalized["source_type"] = str(
        context["source_type"]
    )
    normalized["execution_mode"] = derive_execution_mode(
        context
    )
    normalized["event_role"] = (
        str(context["event_role"])
        if context.get("event_role") is not None
        else None
    )

    normalized["previous_operations"] = [
        _validate_reference(
            reference,
            field_name="previous_operations",
            operation_number=operation_number,
        )
        for reference in (
            context.get(
                "previous_operations",
                [],
            )
            or []
        )
    ]
    normalized["next_operations"] = [
        _validate_reference(
            reference,
            field_name="next_operations",
            operation_number=operation_number,
        )
        for reference in (
            context.get(
                "next_operations",
                [],
            )
            or []
        )
    ]

    normalized["input_documents"] = list(
        context.get(
            "input_documents",
            [],
        )
        or []
    )
    normalized["output_documents"] = list(
        context.get(
            "output_documents",
            [],
        )
        or []
    )
    normalized["business_rules"] = list(
        context.get(
            "business_rules",
            [],
        )
        or []
    )
    normalized["notes"] = _normalize_notes(
        list(
            context.get(
                "notes",
                [],
            )
            or []
        ),
        operation_number=operation_number,
    )
    normalized["branches"] = _normalize_branches(
        list(
            context.get(
                "branches",
                [],
            )
            or []
        ),
        operation_number=operation_number,
    )
    normalized["order_ambiguous"] = bool(
        context.get(
            "order_ambiguous",
            False,
        )
    )
    normalized["validation_issue_codes"] = [
        str(code)
        for code in (
            context.get(
                "validation_issue_codes",
                [],
            )
            or []
        )
    ]

    if not normalized["raw_name"]:
        raise ValueError(
            f"Operation {operation_number} has an empty raw_name."
        )

    return normalized


def load_operation_contexts(
    path: Path,
    *,
    title_override: str | None = None,
) -> LoadedProcedureInput:
    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(payload, dict):
        raise TypeError(
            "operation_contexts.json must contain an object."
        )

    required = {
        "process_id",
        "operation_count",
        "contexts",
    }
    missing = required - payload.keys()

    if missing:
        raise ValueError(
            "operation_contexts.json is missing: "
            + ", ".join(sorted(missing))
        )

    process_id = str(
        payload["process_id"]
    ).strip()

    if not process_id:
        raise ValueError(
            "process_id cannot be empty."
        )

    raw_title = str(
        payload.get(
            "process_title",
            payload.get("title", ""),
        )
    ).strip()

    title = (
        title_override.strip()
        if title_override is not None
        else raw_title
    )

    if not title:
        title = process_id

    raw_contexts = payload["contexts"]

    if not isinstance(raw_contexts, list):
        raise TypeError(
            "contexts must be a list."
        )

    contexts = [
        normalize_context(context)
        for context in raw_contexts
    ]

    expected_count = int(
        payload["operation_count"]
    )

    if expected_count != len(contexts):
        raise ValueError(
            "operation_count does not match "
            "the number of contexts."
        )

    numbers = [
        context["operation_number"]
        for context in contexts
    ]
    ids = [
        context["bpmn_element_id"]
        for context in contexts
    ]

    if len(numbers) != len(set(numbers)):
        raise ValueError(
            "Duplicate operation numbers were found."
        )

    if len(ids) != len(set(ids)):
        raise ValueError(
            "Duplicate BPMN element IDs were found."
        )

    contexts = sorted(
        contexts,
        key=lambda item: item[
            "operation_number"
        ],
    )

    warnings: list[str] = []

    if looks_like_technical_title(
        title,
        process_id,
    ):
        warnings.append(
            "The input title looks like a technical BPMN ID. "
            "Use title_override or fix the context exporter "
            "when a readable procedure title is required."
        )

    return LoadedProcedureInput(
        path=path,
        process_id=process_id,
        title=title,
        contexts=contexts,
        warnings=warnings,
    )
