"""Load and merge deterministic parser outputs."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from narrative_generation.text import normalize_text


@dataclass(frozen=True, slots=True)
class LoadedNarrativeInputs:
    narrative_plan_path: Path
    operation_contexts_path: Path
    narrative_plan: dict
    merge_warnings: list[str]


def read_json_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to read JSON file {path}: {error}") from error

    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}.")

    return payload


def read_json_candidates(
    root: Path,
) -> list[tuple[Path, dict]]:
    candidates: list[tuple[Path, dict]] = []

    for path in sorted(root.rglob("*.json")):
        try:
            payload = read_json_object(path)
        except ValueError:
            continue

        candidates.append((path, payload))

    return candidates


def is_narrative_plan(payload: dict) -> bool:
    return {
        "process_id",
        "process_title",
        "operations",
        "decisions",
        "writing_blocks",
    }.issubset(payload)


def is_operation_contexts(payload: dict) -> bool:
    return {
        "process_id",
        "operation_count",
        "contexts",
    }.issubset(payload)


def select_unique_payload(
    candidates: list[tuple[Path, dict]],
    predicate: Callable[[dict], bool],
    description: str,
) -> tuple[Path, dict]:
    matches = [
        (path, payload)
        for path, payload in candidates
        if predicate(payload)
    ]

    if not matches:
        raise FileNotFoundError(
            f"No {description} JSON file was detected."
        )

    if len(matches) > 1:
        formatted = "\n".join(f"- {path}" for path, _ in matches)
        raise ValueError(
            f"Several {description} files were detected:\n"
            f"{formatted}\nKeep only one version of each input."
        )

    return matches[0]


def detect_input_paths(
    root: Path,
) -> tuple[Path, Path]:
    candidates = read_json_candidates(root)

    narrative_plan_path, _ = select_unique_payload(
        candidates,
        is_narrative_plan,
        "narrative_plan",
    )
    contexts_path, _ = select_unique_payload(
        candidates,
        is_operation_contexts,
        "operation_contexts",
    )

    return narrative_plan_path, contexts_path


def derive_execution_mode(
    plan_operation: dict,
    context: dict,
) -> str:
    existing = str(
        plan_operation.get("execution_mode", "")
    ).strip()

    if existing:
        return existing

    source_type = str(context.get("source_type", "")).casefold()
    element_kind = str(context.get("element_kind", "")).casefold()

    if (
        source_type.endswith("event")
        or element_kind in {"event", "business_event"}
    ):
        return "event"

    if source_type == "servicetask":
        return "automated"

    if source_type in {"usertask", "manualtask"}:
        return "human"

    if (
        source_type in {"callactivity", "subprocess"}
        or element_kind == "subprocess"
    ):
        return "subprocess"

    return "unknown"


def load_and_merge_inputs(
    *,
    narrative_plan_path: Path,
    operation_contexts_path: Path,
) -> LoadedNarrativeInputs:
    narrative_plan = read_json_object(narrative_plan_path)
    operation_contexts = read_json_object(operation_contexts_path)

    if not is_narrative_plan(narrative_plan):
        raise ValueError(
            f"{narrative_plan_path} does not match the narrative plan schema."
        )

    if not is_operation_contexts(operation_contexts):
        raise ValueError(
            f"{operation_contexts_path} does not match the operation contexts schema."
        )

    if narrative_plan["process_id"] != operation_contexts["process_id"]:
        raise ValueError(
            "The two inputs do not describe the same process: "
            f"{narrative_plan['process_id']} != "
            f"{operation_contexts['process_id']}."
        )

    context_by_number: dict[int, dict] = {}

    for context in operation_contexts.get("contexts", []):
        number = int(context["operation_number"])

        if number in context_by_number:
            raise ValueError(
                f"Duplicate operation number in operation_contexts: {number}."
            )

        context_by_number[number] = context

    plan_numbers = [
        int(operation["number"])
        for operation in narrative_plan.get("operations", [])
    ]

    if len(plan_numbers) != len(set(plan_numbers)):
        raise ValueError(
            "The narrative plan contains duplicate operation numbers."
        )

    plan_number_set = set(plan_numbers)
    context_number_set = set(context_by_number)

    if plan_number_set != context_number_set:
        raise ValueError(
            "The operation sets do not match. "
            f"Missing from contexts: "
            f"{sorted(plan_number_set - context_number_set)}; "
            f"missing from plan: "
            f"{sorted(context_number_set - plan_number_set)}."
        )

    merged_operations: list[dict] = []
    merge_warnings: list[str] = []

    for plan_operation in narrative_plan["operations"]:
        number = int(plan_operation["number"])
        context = context_by_number[number]

        plan_name = str(plan_operation.get("raw_name", "")).strip()
        context_name = str(context.get("raw_name", "")).strip()

        if (
            plan_name
            and context_name
            and normalize_text(plan_name) != normalize_text(context_name)
        ):
            merge_warnings.append(
                f"Different names for operation {number}: "
                f"plan={plan_name!r}, context={context_name!r}."
            )

        merged = copy.deepcopy(plan_operation)
        merged["number"] = number
        merged["raw_name"] = plan_name or context_name
        merged["bpmn_element_id"] = context.get("bpmn_element_id")
        merged["element_kind"] = context.get("element_kind")
        merged["source_type"] = context.get("source_type")
        merged["execution_mode"] = derive_execution_mode(
            plan_operation,
            context,
        )
        merged["event_role"] = (
            plan_operation.get("event_role")
            or context.get("event_role")
        )

        if merged["execution_mode"] == "event":
            merged["actor"] = None
        elif merged["execution_mode"] == "automated":
            merged["actor"] = "Le système"
        else:
            merged["actor"] = (
                plan_operation.get("actor")
                or context.get("actor_name")
            )

        for field_name in (
            "notes",
            "business_rules",
            "input_documents",
            "output_documents",
        ):
            merged[field_name] = copy.deepcopy(
                context.get(field_name, [])
                or plan_operation.get(field_name, [])
                or []
            )

        merged["order_ambiguous"] = bool(
            context.get("order_ambiguous", False)
        )
        merged["validation_issue_codes"] = list(
            context.get("validation_issue_codes", []) or []
        )

        merged_operations.append(merged)

    expected_count = int(operation_contexts["operation_count"])

    if expected_count != len(merged_operations):
        raise ValueError(
            "operation_count does not match the number of merged operations."
        )

    merged_plan = copy.deepcopy(narrative_plan)
    merged_plan["operations"] = merged_operations

    return LoadedNarrativeInputs(
        narrative_plan_path=narrative_plan_path,
        operation_contexts_path=operation_contexts_path,
        narrative_plan=merged_plan,
        merge_warnings=merge_warnings,
    )
