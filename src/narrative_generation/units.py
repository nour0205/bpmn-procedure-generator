"""Build ordered narrative units from the narrative plan."""

from __future__ import annotations

import copy
from collections import Counter, defaultdict

from narrative_generation.facts import new_fact, operation_fact
from narrative_generation.text import clean_sentence, normalize_text


DECISION_BLOCK_TYPES = {
    "decision",
    "nested_decision",
    "gateway",
}

SEQUENCE_BLOCK_TYPES = {
    "opening",
    "sequence",
    "convergence",
    "loop",
    "ending",
}


def operation_map(plan: dict) -> dict[int, dict]:
    return {
        int(operation["number"]): operation
        for operation in plan.get("operations", [])
    }


def require_operation(
    operations_by_number: dict[int, dict],
    number: int,
) -> dict:
    normalized = int(number)

    if normalized not in operations_by_number:
        raise ValueError(
            f"Unknown operation number in narrative plan: {normalized}."
        )

    return operations_by_number[normalized]


def decision_map(plan: dict) -> dict[int, dict]:
    result: dict[int, dict] = {}

    for decision in plan.get("decisions", []):
        source_number = decision.get("source_operation_number")

        if source_number is not None:
            result[int(source_number)] = decision

    return result


def branch_label(branch: dict, index: int) -> str:
    value = str(
        branch.get("label")
        or branch.get("condition")
        or f"Branche {index + 1}"
    ).strip()

    normalized = normalize_text(value)

    if normalized == "oui":
        return "Oui"

    if normalized == "non":
        return "Non"

    return value


def ordered_branches(
    plan: dict,
    block: dict,
) -> list[dict]:
    branches = [
        copy.deepcopy(branch)
        for branch in block.get("branches", [])
    ]

    source_number = block.get("source_operation_number")

    if source_number is None:
        return branches

    decision = decision_map(plan).get(int(source_number))

    if decision is None:
        return branches

    remaining = list(branches)
    ordered: list[dict] = []

    for canonical_index, item in enumerate(
        decision.get("branches", [])
    ):
        expected_label = branch_label(item, canonical_index)

        match_index = next(
            (
                index
                for index, candidate in enumerate(remaining)
                if normalize_text(branch_label(candidate, index))
                == normalize_text(expected_label)
            ),
            None,
        )

        if match_index is None:
            continue

        matched = remaining.pop(match_index)
        matched["label"] = expected_label
        ordered.append(matched)

    ordered.extend(remaining)
    return ordered


def explicit_convergence_numbers(plan: dict) -> set[int]:
    result: set[int] = set()

    for block in plan.get("writing_blocks", []):
        if str(block.get("block_type", "")) == "convergence":
            result.update(
                int(number)
                for number in block.get("operation_numbers", [])
            )

    return result


def resolved_structural_operation_numbers(
    plan: dict,
) -> set[int]:
    resolved = set(explicit_convergence_numbers(plan))

    for block in plan.get("writing_blocks", []):
        for branch in block.get("branches", []):
            loop_target = branch.get(
                "loop_back_to_operation_number"
            )

            if loop_target is not None:
                resolved.add(int(loop_target))

    return resolved


def decision_sentence(
    block: dict,
    labels: list[str],
) -> str:
    gateway_name = str(
        block.get("gateway_name") or "Décision"
    ).strip()
    routing_mode = str(
        block.get("routing_mode") or "unknown"
    ).casefold()
    formatted = ", ".join(f"« {label} »" for label in labels)

    if routing_mode == "exclusive":
        return clean_sentence(
            f"La décision « {gateway_name} » distingue "
            "des scénarios alternatifs"
            + (f" : {formatted}" if formatted else "")
        )

    if routing_mode == "parallel":
        return clean_sentence(
            f"La passerelle « {gateway_name} » ouvre "
            "des branches exécutées en parallèle"
        )

    if routing_mode == "inclusive":
        return clean_sentence(
            f"La décision « {gateway_name} » permet "
            "d’activer un ou plusieurs scénarios"
            + (f" parmi {formatted}" if formatted else "")
        )

    return clean_sentence(
        f"La décision « {gateway_name} » organise la suite du flux"
        + (
            f" selon les scénarios {formatted}"
            if formatted
            else ""
        )
    )


def build_narrative_units(
    plan: dict,
) -> tuple[list[dict], dict, list[str]]:
    """Build units while keeping nested decisions inside their parent branch."""

    operations_by_number = operation_map(plan)
    convergence_numbers = explicit_convergence_numbers(plan)
    resolved_structural_numbers = (
        resolved_structural_operation_numbers(plan)
    )

    units: list[dict] = []
    owned_numbers: list[int] = []
    referenced_numbers: list[int] = []
    build_warnings: list[str] = []

    blocks = sorted(
        plan.get("writing_blocks", []),
        key=lambda block: int(block.get("order", 0)),
    )

    nested_by_parent: dict[
        tuple[int, str],
        list[dict],
    ] = defaultdict(list)

    for block in blocks:
        parent_source = block.get(
            "parent_decision_source_number"
        )
        parent_label = block.get("parent_branch_label")

        if parent_source is None or not parent_label:
            continue

        nested_by_parent[
            (
                int(parent_source),
                normalize_text(str(parent_label)),
            )
        ].append(block)

    emitted_orders: set[int] = set()

    def emit_sequence_block(block: dict) -> None:
        block_order = int(block.get("order", 0))
        block_type = str(block.get("block_type", ""))
        numbers = [
            int(number)
            for number in block.get(
                "operation_numbers",
                [],
            )
        ]
        facts = [
            operation_fact(
                require_operation(
                    operations_by_number,
                    number,
                )
            )
            for number in numbers
        ]

        if not facts:
            return

        prefix = (
            "À l’issue des différents scénarios, "
            if block_type == "convergence"
            else None
        )

        units.append(
            {
                "unit_id": f"block_{block_order}_{block_type}",
                "block_order": block_order,
                "unit_type": block_type,
                "branch_label": None,
                "prefix": prefix,
                "facts": facts,
                "owned_operation_numbers": numbers,
                "referenced_operation_numbers": [],
            }
        )
        owned_numbers.extend(numbers)

    def emit_decision_block(block: dict) -> None:
        block_order = int(block.get("order", 0))
        block_type = str(block.get("block_type", ""))
        source_operation = require_operation(
            operations_by_number,
            block["source_operation_number"],
        )
        branches = ordered_branches(plan, block)
        labels = [
            branch_label(branch, index)
            for index, branch in enumerate(branches)
        ]
        source_number = int(source_operation["number"])

        decision_prefix = None

        if (
            block_type == "nested_decision"
            and block.get("parent_branch_label")
        ):
            decision_prefix = (
                "Dans le prolongement du scénario "
                f"« {branch_label({'label': block['parent_branch_label']}, 0)} », "
            )

        units.append(
            {
                "unit_id": f"block_{block_order}_decision",
                "block_order": block_order,
                "unit_type": "decision",
                "branch_label": None,
                "prefix": decision_prefix,
                "facts": [
                    operation_fact(source_operation),
                    new_fact(
                        fact_id=(
                            f"block_{block_order}_decision_rule"
                        ),
                        kind="decision",
                        text=decision_sentence(block, labels),
                        locked=True,
                        source_text=(
                            str(block.get("gateway_name", ""))
                            + " "
                            + " ".join(labels)
                        ),
                    ),
                ],
                "owned_operation_numbers": [source_number],
                "referenced_operation_numbers": [],
            }
        )
        owned_numbers.append(source_number)

        for branch_index, branch in enumerate(branches):
            label = branch_label(branch, branch_index)
            branch_numbers = [
                int(number)
                for number in branch.get(
                    "operation_numbers",
                    [],
                )
            ]
            facts = [
                operation_fact(
                    require_operation(
                        operations_by_number,
                        number,
                    )
                )
                for number in branch_numbers
            ]

            loop_target_number = branch.get(
                "loop_back_to_operation_number"
            )
            nested_decisions = [
                int(number)
                for number in branch.get(
                    "nested_decision_source_numbers",
                    [],
                )
            ]
            convergence_number = branch.get(
                "convergence_operation_number"
            )
            referenced: list[int] = []

            if loop_target_number is not None:
                target = require_operation(
                    operations_by_number,
                    loop_target_number,
                )
                facts.append(
                    new_fact(
                        fact_id=(
                            f"block_{block_order}_"
                            f"branch_{branch_index + 1}_loop"
                        ),
                        kind="loop",
                        text=(
                            "Le flux revient à l’activité "
                            f"« {target['raw_name']} »"
                        ),
                        locked=True,
                        source_text=str(target["raw_name"]),
                    )
                )
                referenced = [int(loop_target_number)]

            elif (
                convergence_number is not None
                and not nested_decisions
                and int(convergence_number)
                not in convergence_numbers
            ):
                target = require_operation(
                    operations_by_number,
                    convergence_number,
                )
                facts.append(
                    new_fact(
                        fact_id=(
                            f"block_{block_order}_"
                            f"branch_{branch_index + 1}_"
                            "convergence"
                        ),
                        kind="convergence_reference",
                        text=(
                            "Le flux rejoint l’activité commune "
                            f"« {target['raw_name']} »"
                        ),
                        locked=True,
                        source_text=str(target["raw_name"]),
                    )
                )
                referenced = [int(convergence_number)]

            if not facts:
                facts.append(
                    new_fact(
                        fact_id=(
                            f"block_{block_order}_"
                            f"branch_{branch_index + 1}_empty"
                        ),
                        kind="empty_branch",
                        text=(
                            "Le flux se poursuit directement "
                            "vers la suite prévue par le processus"
                        ),
                        locked=True,
                        source_text=label,
                    )
                )

            branch_prefix = f"Dans le scénario « {label} », "

            if (
                block_type == "nested_decision"
                and normalize_text(
                    str(block.get("gateway_name", ""))
                ).startswith("validation")
            ):
                branch_prefix = (
                    "En cas de validation, "
                    if normalize_text(label) == "oui"
                    else "En cas de refus de validation, "
                )

            units.append(
                {
                    "unit_id": (
                        f"block_{block_order}_"
                        f"branch_{branch_index + 1}"
                    ),
                    "block_order": block_order,
                    "unit_type": "decision_branch",
                    "branch_label": label,
                    "prefix": branch_prefix,
                    "facts": facts,
                    "owned_operation_numbers": branch_numbers,
                    "referenced_operation_numbers": referenced,
                }
            )
            owned_numbers.extend(branch_numbers)
            referenced_numbers.extend(referenced)

            nested_blocks = nested_by_parent.get(
                (
                    source_number,
                    normalize_text(label),
                ),
                [],
            )

            for nested_block in nested_blocks:
                emit_block(nested_block)

    def emit_block(block: dict) -> None:
        block_order = int(block.get("order", 0))

        if block_order in emitted_orders:
            return

        emitted_orders.add(block_order)
        block_type = str(block.get("block_type", ""))

        if block_type in DECISION_BLOCK_TYPES:
            emit_decision_block(block)
        elif block_type in SEQUENCE_BLOCK_TYPES:
            emit_sequence_block(block)
        else:
            raise ValueError(
                "Unsupported narrative block type: "
                f"{block_type!r}."
            )

    # Emit only top-level blocks first. Nested blocks are inserted directly
    # after the parent branch that contains them.
    for block in blocks:
        if block.get("parent_decision_source_number") is None:
            emit_block(block)

    # Defensive coverage for malformed/legacy plans.
    for block in blocks:
        emit_block(block)

    expected_numbers = set(operations_by_number)
    owned_set = set(owned_numbers)

    missing = sorted(expected_numbers - owned_set)
    unknown = sorted(owned_set - expected_numbers)
    duplicates = sorted(
        number
        for number, count in Counter(owned_numbers).items()
        if count > 1
    )

    if missing or unknown or duplicates:
        raise ValueError(
            "Invalid deterministic narrative coverage. "
            f"missing={missing}; unknown={unknown}; "
            f"duplicated={duplicates}."
        )

    for operation in plan.get("operations", []):
        if (
            operation.get("order_ambiguous")
            and int(operation["number"])
            not in resolved_structural_numbers
        ):
            build_warnings.append(
                f"Operation {operation['number']} is marked "
                "as order-ambiguous by the parser."
            )

    coverage = {
        "expected_operation_numbers": sorted(expected_numbers),
        "owned_operation_numbers": sorted(owned_set),
        "referenced_operation_numbers": sorted(
            set(referenced_numbers)
        ),
        "missing_operation_numbers": missing,
        "duplicated_operation_numbers": duplicates,
    }

    return units, coverage, build_warnings
