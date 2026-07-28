"""Build an explicit deterministic narrative plan."""

from __future__ import annotations

from collections import deque

from .narrative_models import (
    NarrativeBranch,
    NarrativeContext,
    NarrativeOperation,
)
from .narrative_plan_models import (
    NarrativePlan,
    NarrativePlanBranch,
    NarrativePlanConvergence,
    NarrativePlanDecision,
    NarrativePlanOperation,
    NarrativeWritingBlock,
    NarrativeWritingBranch,
)


class NarrativePlanBuilder:
    """
    Convert a flat NarrativeContext into an explicit writing plan.

    The builder identifies:

    - entry and terminal operations;
    - decisions and their branches;
    - loop-back branches;
    - branch paths;
    - convergence operations.
    """

    def build(
        self,
        context: NarrativeContext,
    ) -> NarrativePlan:
        operations_by_number = {
            operation.number: operation
            for operation in context.operations
        }

        decision_numbers = {
            operation.number
            for operation in context.operations
            if operation.branches
        }

        loop_back_edges = (
            self._collect_loop_back_edges(
                context.operations
            )
        )

        convergence_numbers = (
            self._find_structural_convergences(
                operations=context.operations,
                loop_back_edges=loop_back_edges,
            )
        )

        adjacency = self._build_forward_adjacency(
            context.operations
        )

        compact_operations = [
            self._build_plan_operation(operation)
            for operation in context.operations
        ]

        decisions = [
            self._build_decision(
                operation=operation,
                operations_by_number=(
                    operations_by_number
                ),
                adjacency=adjacency,
                decision_numbers=decision_numbers,
                convergence_numbers=(
                    convergence_numbers
                ),
            )
            for operation in context.operations
            if operation.branches
        ]

        convergences = [
            NarrativePlanConvergence(
                operation_number=operation.number,
                operation_name=operation.raw_name,
                incoming_operation_numbers=[
                    previous_number
                    for previous_number
                    in operation.previous_operation_numbers
                    if (
                        previous_number,
                        operation.number,
                    )
                    not in loop_back_edges
                ],
            )
            for operation in context.operations
            if operation.number in convergence_numbers
        ]

        entry_operation_numbers = [
            operation.number
            for operation in context.operations
            if not operation.previous_operation_numbers
        ]

        writing_blocks = self._build_writing_blocks(
            operations=context.operations,
            decisions=decisions,
            convergence_numbers=convergence_numbers,
            adjacency=adjacency,
            entry_operation_numbers=(
                entry_operation_numbers
            ),
        )

        terminal_operation_numbers = [
            operation.number
            for operation in context.operations
            if not operation.next_operation_numbers
        ]

        return NarrativePlan(
            process_id=context.process_id,
            process_title=context.process_title,
            end_event_status=(
                context.end_event_status
            ),
            entry_operation_numbers=(
                entry_operation_numbers
            ),
            terminal_operation_numbers=(
                terminal_operation_numbers
            ),
            operations=compact_operations,
            decisions=decisions,
            convergences=convergences,
            writing_blocks=writing_blocks,
        )

    @staticmethod
    def _collect_loop_back_edges(
        operations: list[NarrativeOperation],
    ) -> set[tuple[int, int]]:
        """
        Collect explicit loop-back edges.

        Each tuple represents:
        source operation -> loop target operation.
        """

        edges: set[tuple[int, int]] = set()

        for operation in operations:
            for target_number in (
                operation.loop_target_operation_numbers
            ):
                edges.add(
                    (
                        operation.number,
                        target_number,
                    )
                )

            for branch in operation.branches:
                if (
                    branch.is_loop_back
                    and branch.target_operation_number
                    is not None
                ):
                    edges.add(
                        (
                            operation.number,
                            branch.target_operation_number,
                        )
                    )

        return edges

    @staticmethod
    def _find_structural_convergences(
        *,
        operations: list[NarrativeOperation],
        loop_back_edges: set[tuple[int, int]],
    ) -> set[int]:
        """
        Identify true convergences after excluding loop-back inputs.

        A node is a structural convergence only when at least two
        distinct forward paths enter it.
        """

        convergence_numbers: set[int] = set()

        for operation in operations:
            forward_predecessors = {
                previous_number
                for previous_number
                in operation.previous_operation_numbers
                if (
                    previous_number,
                    operation.number,
                )
                not in loop_back_edges
            }

            if len(forward_predecessors) > 1:
                convergence_numbers.add(
                    operation.number
                )

        return convergence_numbers

    def _build_writing_blocks(
        self,
        *,
        operations: list[NarrativeOperation],
        decisions: list[NarrativePlanDecision],
        convergence_numbers: set[int],
        adjacency: dict[int, list[int]],
        entry_operation_numbers: list[int],
    ) -> list[NarrativeWritingBlock]:
        """
        Build a complete writing plan in graph order.

        Decision blocks cover their source operation and branch paths.
        Convergence blocks cover shared continuation nodes. Ordinary
        operations that remain outside those structural blocks are grouped
        into sequence blocks.

        Traversal resumes after every convergence, which prevents operations
        following a decision from disappearing from the narrative plan.
        """

        decisions_by_source = {
            decision.source_operation_number: decision
            for decision in decisions
        }

        decision_source_numbers = set(
            decisions_by_source
        )

        operation_numbers = [
            operation.number
            for operation in operations
        ]

        parent_by_nested_decision: dict[
            int,
            tuple[int, str],
        ] = {}

        for decision in decisions:
            for branch in decision.branches:
                for operation_number in (
                    branch.path_operation_numbers
                ):
                    if (
                        operation_number
                        in decision_source_numbers
                        and operation_number
                        != decision.source_operation_number
                    ):
                        parent_by_nested_decision.setdefault(
                            operation_number,
                            (
                                decision.source_operation_number,
                                branch.label,
                            ),
                        )

        blocks: list[NarrativeWritingBlock] = []
        covered_operations: set[int] = set()
        emitted_decisions: set[int] = set()
        emitted_convergences: set[int] = set()
        active_paths: set[int] = set()

        def next_order() -> int:
            return len(blocks) + 1

        def append_sequence(
            numbers: list[int],
        ) -> None:
            sequence_numbers = [
                number
                for number in numbers
                if number not in covered_operations
            ]

            if not sequence_numbers:
                return

            blocks.append(
                NarrativeWritingBlock(
                    order=next_order(),
                    block_type="sequence",
                    operation_numbers=sequence_numbers,
                )
            )

            covered_operations.update(
                sequence_numbers
            )

        def append_convergence(
            number: int,
        ) -> None:
            if number in emitted_convergences:
                return

            blocks.append(
                NarrativeWritingBlock(
                    order=next_order(),
                    block_type="convergence",
                    operation_numbers=[number],
                )
            )

            emitted_convergences.add(number)
            covered_operations.add(number)

        def build_decision_block(
            decision: NarrativePlanDecision,
        ) -> tuple[
            NarrativeWritingBlock,
            list[int],
        ]:
            source_number = (
                decision.source_operation_number
            )

            parent_information = (
                parent_by_nested_decision.get(
                    source_number
                )
            )

            writing_branches: list[
                NarrativeWritingBranch
            ] = []

            nested_sources_in_order: list[int] = []

            for branch in self._order_writing_branches(
                decision.branches
            ):
                nested_sources = [
                    operation_number
                    for operation_number
                    in branch.path_operation_numbers
                    if (
                        operation_number
                        in decision_source_numbers
                        and operation_number
                        != source_number
                    )
                ]

                normal_operations = [
                    operation_number
                    for operation_number
                    in branch.path_operation_numbers
                    if operation_number not in nested_sources
                ]

                # A loop target is a reference to an already narrated step,
                # not a new forward operation.
                if branch.is_loop_back:
                    normal_operations = []

                for nested_source in nested_sources:
                    if (
                        nested_source
                        not in nested_sources_in_order
                    ):
                        nested_sources_in_order.append(
                            nested_source
                        )

                writing_branches.append(
                    NarrativeWritingBranch(
                        label=branch.label,
                        condition=branch.condition,
                        operation_numbers=normal_operations,
                        nested_decision_source_numbers=(
                            nested_sources
                        ),
                        is_loop_back=branch.is_loop_back,
                        loop_back_to_operation_number=(
                            branch.loop_back_to_operation_number
                        ),
                        convergence_operation_number=(
                            branch.converges_to_operation_number
                        ),
                    )
                )

                covered_operations.update(
                    normal_operations
                )

            covered_operations.add(
                source_number
            )

            return (
                NarrativeWritingBlock(
                    order=next_order(),
                    block_type=(
                        "nested_decision"
                        if parent_information
                        else "decision"
                    ),
                    source_operation_number=source_number,
                    parent_decision_source_number=(
                        parent_information[0]
                        if parent_information
                        else None
                    ),
                    parent_branch_label=(
                        parent_information[1]
                        if parent_information
                        else None
                    ),
                    gateway_name=decision.gateway_name,
                    routing_mode=decision.routing_mode,
                    branches=writing_branches,
                    convergence_operation_number=(
                        decision.shared_convergence_operation_number
                    ),
                ),
                nested_sources_in_order,
            )

        def emit_path(
            start_number: int,
            *,
            stop_number: int | None = None,
        ) -> None:
            if start_number == stop_number:
                return

            if start_number in covered_operations:
                return

            if start_number in active_paths:
                return

            active_paths.add(start_number)

            sequence: list[int] = []
            current = start_number
            locally_seen: set[int] = set()

            try:
                while (
                    current not in locally_seen
                    and current != stop_number
                    and current not in covered_operations
                ):
                    locally_seen.add(current)

                    decision = decisions_by_source.get(
                        current
                    )

                    if decision is not None:
                        append_sequence(sequence)
                        sequence = []

                        emit_decision(
                            current,
                            stop_number=stop_number,
                        )
                        return

                    if current in convergence_numbers:
                        append_sequence(sequence)
                        sequence = []

                        append_convergence(current)

                        for next_number in adjacency.get(
                            current,
                            [],
                        ):
                            emit_path(
                                next_number,
                                stop_number=stop_number,
                            )

                        return

                    sequence.append(current)

                    next_numbers = [
                        number
                        for number in adjacency.get(
                            current,
                            [],
                        )
                        if (
                            number != stop_number
                            and number
                            not in covered_operations
                        )
                    ]

                    if len(next_numbers) == 1:
                        current = next_numbers[0]
                        continue

                    append_sequence(sequence)
                    sequence = []

                    for next_number in next_numbers:
                        emit_path(
                            next_number,
                            stop_number=stop_number,
                        )

                    return

                append_sequence(sequence)

            finally:
                active_paths.discard(
                    start_number
                )

        def emit_decision(
            source_number: int,
            *,
            stop_number: int | None = None,
        ) -> None:
            if source_number in emitted_decisions:
                return

            decision = decisions_by_source.get(
                source_number
            )

            if decision is None:
                emit_path(
                    source_number,
                    stop_number=stop_number,
                )
                return

            decision_block, nested_sources = (
                build_decision_block(decision)
            )

            blocks.append(decision_block)
            emitted_decisions.add(
                source_number
            )

            continuation_stop = (
                decision.shared_convergence_operation_number
                or stop_number
            )

            for nested_source in nested_sources:
                emit_decision(
                    nested_source,
                    stop_number=continuation_stop,
                )

            shared_convergence = (
                decision.shared_convergence_operation_number
            )

            if (
                shared_convergence is not None
                and shared_convergence != stop_number
            ):
                append_convergence(
                    shared_convergence
                )

                for next_number in adjacency.get(
                    shared_convergence,
                    [],
                ):
                    emit_path(
                        next_number,
                        stop_number=stop_number,
                    )

        for entry_number in entry_operation_numbers:
            emit_path(entry_number)

        # Preserve disconnected or structurally unusual components while
        # still guaranteeing complete deterministic coverage.
        for operation_number in operation_numbers:
            if operation_number not in covered_operations:
                emit_path(operation_number)

        missing_operations = (
            set(operation_numbers)
            - covered_operations
        )

        if missing_operations:
            raise ValueError(
                "Narrative writing plan does not cover operations: "
                + ", ".join(
                    str(number)
                    for number in sorted(
                        missing_operations
                    )
                )
            )

        return blocks

    @staticmethod
    def _order_writing_branches(
        branches: list[NarrativePlanBranch],
    ) -> list[NarrativePlanBranch]:
        """
        Put rejection/no branches before acceptance/yes branches.

        This allows validation loops to be described before the accepted
        continuation and prevents the accepted sequence from being repeated.
        """

        negative_labels = {
            "non",
            "no",
            "false",
            "faux",
            "refus",
            "rejet",
            "rejeté",
            "refusé",
        }

        positive_labels = {
            "oui",
            "yes",
            "true",
            "vrai",
            "accepté",
            "validé",
        }

        def branch_priority(
            indexed_branch: tuple[
                int,
                NarrativePlanBranch,
            ],
        ) -> tuple[int, int]:
            index, branch = indexed_branch

            normalized_label = (
                branch.label
                .strip()
                .casefold()
            )

            if normalized_label in negative_labels:
                priority = 0

            elif normalized_label in positive_labels:
                priority = 1

            else:
                priority = 2

            return priority, index

        ordered = sorted(
            enumerate(branches),
            key=branch_priority,
        )

        return [
            branch
            for _, branch in ordered
        ]

    @staticmethod
    def _build_plan_operation(
        operation: NarrativeOperation,
    ) -> NarrativePlanOperation:
        """Create a compact operation representation."""

        return NarrativePlanOperation(
            number=operation.number,
            raw_name=operation.raw_name,
            actor=operation.actor,
            execution_mode=(
                operation.execution_mode
            ),
            event_role=operation.event_role,
            previous_operation_numbers=(
                operation.previous_operation_numbers
            ),
            next_operation_numbers=(
                operation.next_operation_numbers
            ),
            notes=operation.notes,
            business_rules=(
                operation.business_rules
            ),
            input_documents=(
                operation.input_documents
            ),
            output_documents=(
                operation.output_documents
            ),
        )

    def _build_decision(
        self,
        *,
        operation: NarrativeOperation,
        operations_by_number: dict[
            int,
            NarrativeOperation,
        ],
        adjacency: dict[int, list[int]],
        decision_numbers: set[int],
        convergence_numbers: set[int],
    ) -> NarrativePlanDecision:
        """Build one explicit decision block."""

        plan_branches: list[
            NarrativePlanBranch
        ] = []

        non_loop_convergences: list[
            int
        ] = []

        for branch in operation.branches:
            target_number = (
                branch.target_operation_number
            )

            if target_number is None:
                continue

            if branch.is_loop_back:
                path = [target_number]
                convergence_number = None

            else:
                convergence_number = (
                    self._first_reachable_convergence(
                        start=target_number,
                        adjacency=adjacency,
                        convergence_numbers=(
                            convergence_numbers
                        ),
                    )
                )

                path = self._trace_branch_path(
                    start=target_number,
                    stop=convergence_number,
                    adjacency=adjacency,
                    decision_numbers=(
                        decision_numbers
                    ),
                )

                if convergence_number is not None:
                    non_loop_convergences.append(
                        convergence_number
                    )

            target_operation = (
                operations_by_number.get(
                    target_number
                )
            )

            target_name = (
                target_operation.raw_name
                if target_operation
                else branch.target_operation_name
            )

            plan_branches.append(
                NarrativePlanBranch(
                    label=branch.label,
                    condition=branch.condition,
                    target_operation_number=(
                        target_number
                    ),
                    target_operation_name=(
                        target_name
                    ),
                    path_operation_numbers=path,
                    is_loop_back=(
                        branch.is_loop_back
                    ),
                    loop_back_to_operation_number=(
                        target_number
                        if branch.is_loop_back
                        else None
                    ),
                    converges_to_operation_number=(
                        convergence_number
                    ),
                )
            )

        shared_convergence = (
            self._shared_convergence(
                non_loop_convergences
            )
        )

        gateway_name = next(
            (
                branch.gateway_name
                for branch in operation.branches
                if branch.gateway_name
            ),
            None,
        )

        return NarrativePlanDecision(
            source_operation_number=(
                operation.number
            ),
            gateway_name=gateway_name,
            routing_mode=(
                self._determine_routing_mode(
                    operation.branches
                )
            ),
            branches=plan_branches,
            shared_convergence_operation_number=(
                shared_convergence
            ),
        )

    @staticmethod
    def _build_forward_adjacency(
        operations: list[NarrativeOperation],
    ) -> dict[int, list[int]]:
        """
        Build graph adjacency while excluding explicit loop-back edges.

        Loop edges remain represented separately in decision branches.
        """

        adjacency: dict[int, list[int]] = {}

        for operation in operations:
            loop_targets = set(
                operation.loop_target_operation_numbers
            )

            loop_targets.update(
                branch.target_operation_number
                for branch in operation.branches
                if (
                    branch.is_loop_back
                    and branch.target_operation_number
                    is not None
                )
            )

            adjacency[operation.number] = [
                target
                for target
                in operation.next_operation_numbers
                if target not in loop_targets
            ]

        return adjacency

    @staticmethod
    def _trace_branch_path(
        *,
        start: int,
        stop: int | None,
        adjacency: dict[int, list[int]],
        decision_numbers: set[int],
    ) -> list[int]:
        """
        Follow a linear branch until a convergence or nested decision.

        A nested decision is included in the path but its own branches
        are represented separately in the plan.
        """

        path: list[int] = []
        visited: set[int] = set()

        current = start

        while current not in visited:
            if current == stop:
                break

            visited.add(current)
            path.append(current)

            if (
                current in decision_numbers
                and current != start
            ):
                break

            next_operations = adjacency.get(
                current,
                [],
            )

            if len(next_operations) != 1:
                break

            next_operation = next_operations[0]

            if next_operation == stop:
                break

            current = next_operation

        return path

    @staticmethod
    def _first_reachable_convergence(
        *,
        start: int,
        adjacency: dict[int, list[int]],
        convergence_numbers: set[int],
    ) -> int | None:
        """Return the nearest convergence reachable from a branch."""

        queue: deque[int] = deque([start])
        visited: set[int] = set()

        while queue:
            current = queue.popleft()

            if current in visited:
                continue

            visited.add(current)

            if current in convergence_numbers:
                return current

            queue.extend(
                adjacency.get(
                    current,
                    [],
                )
            )

        return None

    @staticmethod
    def _shared_convergence(
        convergence_numbers: list[int],
    ) -> int | None:
        """
        Return a shared convergence only when at least two
        non-loop branches reach the same operation.
        """

        if len(convergence_numbers) < 2:
            return None

        first = convergence_numbers[0]

        if all(
            number == first
            for number in convergence_numbers
        ):
            return first

        return None

    @staticmethod
    def _determine_routing_mode(
        branches: list[NarrativeBranch],
    ) -> str:
        """
        Infer an exclusive decision only for explicit yes/no branches.

        Other gateway types remain unknown until gateway_type is
        exported deterministically by the parser.
        """

        normalized_labels = {
            branch.label
            .strip()
            .casefold()
            for branch in branches
        }

        yes_labels = {
            "oui",
            "yes",
            "vrai",
            "true",
        }

        no_labels = {
            "non",
            "no",
            "faux",
            "false",
        }

        has_yes = bool(
            normalized_labels & yes_labels
        )

        has_no = bool(
            normalized_labels & no_labels
        )

        if has_yes and has_no:
            return "exclusive"

        if any(
            branch.is_default
            for branch in branches
        ):
            return "exclusive"

        return "unknown"