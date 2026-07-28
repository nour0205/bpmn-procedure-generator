"""Build deterministic narrative context from operation contexts."""

from __future__ import annotations

from typing import Any

from .narrative_models import (
    NarrativeBranch,
    NarrativeContext,
    NarrativeOperation,
)


class NarrativeContextBuilder:
    """
    Build narrative context directly from deterministic operation contexts.

    This builder does not depend on generated procedure descriptions or on
    DocumentBundle.
    """

    OPERATION_LIST_KEYS = (
        "operations",
        "operation_contexts",
        "contexts",
    )

    NUMBER_KEYS = (
        "operation_number",
        "number",
    )

    ID_KEYS = (
        "bpmn_element_id",
        "id",
        "element_id",
    )

    ACTOR_KEYS = (
        "actor_name",
        "actor",
        "executor",
    )

    NAME_KEYS = (
        "raw_name",
        "name",
        "operation_name",
    )

    DESCRIPTION_KEYS = (
        "description",
        "generated_description",
        "operation_description",
        "enriched_description",
    )

    PREVIOUS_KEYS = (
        "previous_operations",
        "previous_operation_ids",
        "previous",
    )

    NEXT_KEYS = (
        "next_operations",
        "next_operation_ids",
        "next",
    )

    BRANCH_KEYS = (
        "branches",
        "decision_branches",
        "gateway_branches",
    )

    def build(
        self,
        raw_data: dict[str, Any] | list[Any],
        *,
        default_process_id: str,
        default_process_title: str,
        process_title_override: str | None = None,
    ) -> NarrativeContext:
        """Build a complete deterministic context."""

        metadata = self._extract_metadata(raw_data)
        raw_operations = self._extract_operations(raw_data)

        process_id = self._first_non_empty(
            metadata.get("process_id"),
            metadata.get("id"),
            default_process_id,
        )

        metadata_title = self._first_non_empty(
            metadata.get("process_title"),
            metadata.get("process_name"),
            metadata.get("title"),
            metadata.get("name"),
        )

        if (
            isinstance(metadata_title, str)
            and metadata_title.startswith(
                (
                    "Id_",
                    "Process_",
                    "Activity_",
                )
            )
        ):
            metadata_title = None

        process_title = self._first_non_empty(
            process_title_override,
            metadata_title,
            default_process_title,
        )

        numbered_operations = self._assign_numbers(
            raw_operations
        )

        operation_number_by_id = {
            operation_id: number
            for number, operation_id, _ in numbered_operations
            if operation_id
        }

        operations = [
            self._build_operation(
                number=number,
                operation_id=operation_id,
                raw_operation=raw_operation,
                operation_number_by_id=(
                    operation_number_by_id
                ),
            )
            for (
                number,
                operation_id,
                raw_operation,
            ) in numbered_operations
        ]

        actors = list(
            dict.fromkeys(
                operation.actor
                for operation in operations
                if operation.actor
            )
        )

        documents = list(
            dict.fromkeys(
                document
                for operation in operations
                for document in (
                    operation.input_documents
                    + operation.output_documents
                )
                if document
            )
        )

        business_rules = list(
            dict.fromkeys(
                rule
                for operation in operations
                for rule in operation.business_rules
                if rule
            )
        )

        return NarrativeContext(
            process_id=str(process_id),
            process_title=str(process_title),
            end_event_status=(
                self._determine_end_event_status(
                    raw_data=raw_data,
                    operations=operations,
                )
            ),
            actors=actors,
            operations=operations,
            documents=documents,
            business_rules=business_rules,
        )

    def _build_operation(
        self,
        *,
        number: int,
        operation_id: str | None,
        raw_operation: dict[str, Any],
        operation_number_by_id: dict[str, int],
    ) -> NarrativeOperation:
        """Convert one raw operation context."""

        raw_name = str(
            self._get_first(
                raw_operation,
                self.NAME_KEYS,
                default=f"Opération {number}",
            )
        ).strip()

        actor = self._clean_optional_text(
            self._get_first(
                raw_operation,
                self.ACTOR_KEYS,
            )
        )

        element_kind = str(
            raw_operation.get(
                "element_kind",
                "operation",
            )
        ).strip()

        source_type = self._clean_optional_text(
            raw_operation.get("source_type")
        )

        execution_mode = self._execution_mode(
            element_kind=element_kind,
            source_type=source_type,
            actor=actor,
        )

        event_role = self._event_role(
            execution_mode=execution_mode,
            source_type=source_type,
        )

        lane_context: str | None = None
        executor = actor

        # A lane containing an event or service task is contextual.
        # It must not automatically be treated as the executor.
        if execution_mode in {
            "event",
            "automated",
        }:
            lane_context = actor

        if execution_mode == "event":
            executor = None

        elif execution_mode == "automated":
            executor = "Le système"

        previous_numbers = self._resolve_references(
            self._get_first(
                raw_operation,
                self.PREVIOUS_KEYS,
                default=[],
            ),
            operation_number_by_id,
        )

        next_numbers = self._resolve_references(
            self._get_first(
                raw_operation,
                self.NEXT_KEYS,
                default=[],
            ),
            operation_number_by_id,
        )

        branches = self._build_branches(
            raw_operation=raw_operation,
            current_operation_number=number,
            operation_number_by_id=(
                operation_number_by_id
            ),
        )

        loop_targets = list(
            dict.fromkeys(
                branch.target_operation_number
                for branch in branches
                if (
                    branch.target_operation_number
                    is not None
                    and branch.is_loop_back
                )
            )
        )

        description = self._clean_optional_text(
            self._get_first(
                raw_operation,
                self.DESCRIPTION_KEYS,
            )
        )

        # Generated descriptions are not authoritative for events.
        if execution_mode == "event":
            description = None

        # The raw subprocess name is enough for the narrative.
        # Removing generated wording avoids repeating the previous step.
        if execution_mode == "subprocess":
            description = None

        business_rules = self._extract_text_list(
            raw_operation.get(
                "business_rules",
                [],
            )
        )

        notes = self._extract_text_list(
            raw_operation.get(
                "notes",
                [],
            )
        )

        input_documents = self._extract_document_names(
            self._get_first(
                raw_operation,
                (
                    "input_documents",
                    "input_document_names",
                ),
                default=[],
            )
        )

        output_documents = self._extract_document_names(
            self._get_first(
                raw_operation,
                (
                    "output_documents",
                    "output_document_names",
                ),
                default=[],
            )
        )

        return NarrativeOperation(
            number=number,
            bpmn_element_id=operation_id,
            actor=executor,
            lane_context=lane_context,
            raw_name=raw_name,
            description=description,
            element_kind=element_kind,
            source_type=source_type,
            execution_mode=execution_mode,
            event_role=event_role,
            previous_operation_numbers=previous_numbers,
            next_operation_numbers=next_numbers,
            loop_target_operation_numbers=loop_targets,
            is_divergence=(
                len(next_numbers) > 1
                or len(branches) > 1
            ),
            is_convergence=(
                len(previous_numbers) > 1
            ),
            branches=branches,
            business_rules=business_rules,
            notes=notes,
            input_documents=input_documents,
            output_documents=output_documents,
        )

    def _build_branches(
        self,
        *,
        raw_operation: dict[str, Any],
        current_operation_number: int,
        operation_number_by_id: dict[str, int],
    ) -> list[NarrativeBranch]:
        """Build decision branches from available context fields."""

        raw_branches = self._get_first(
            raw_operation,
            self.BRANCH_KEYS,
            default=[],
        )

        if not isinstance(raw_branches, list):
            return []

        branches: list[NarrativeBranch] = []

        for raw_branch in raw_branches:
            if not isinstance(raw_branch, dict):
                continue

            target_id = self._clean_optional_text(
                self._first_non_empty(
                    raw_branch.get(
                        "target_operation_id"
                    ),
                    raw_branch.get(
                        "target_element_id"
                    ),
                    raw_branch.get("target_id"),
                    raw_branch.get("target"),
                )
            )

            target_number = raw_branch.get(
                "target_operation_number"
            )

            if (
                not isinstance(target_number, int)
                and target_id
            ):
                target_number = (
                    operation_number_by_id.get(
                        target_id
                    )
                )

            target_name = self._first_non_empty(
                raw_branch.get(
                    "target_operation_name"
                ),
                raw_branch.get("target_name"),
                raw_branch.get("name"),
                target_id,
                "Destination non précisée",
            )

            condition = self._clean_optional_text(
                raw_branch.get("condition")
            )

            label = self._first_non_empty(
                raw_branch.get("label"),
                condition,
                "Branche non libellée",
            )

            branches.append(
                NarrativeBranch(
                    gateway_name=(
                        self._clean_optional_text(
                            raw_branch.get(
                                "gateway_name"
                            )
                        )
                    ),
                    label=str(label),
                    condition=condition,
                    is_default=bool(
                        raw_branch.get(
                            "is_default",
                            False,
                        )
                    ),
                    target_operation_number=(
                        target_number
                        if isinstance(
                            target_number,
                            int,
                        )
                        else None
                    ),
                    target_operation_name=str(
                        target_name
                    ),
                    is_loop_back=bool(
                        isinstance(
                            target_number,
                            int,
                        )
                        and target_number
                        <= current_operation_number
                    ),
                )
            )

        return branches

    @staticmethod
    def _extract_metadata(
        raw_data: dict[str, Any] | list[Any],
    ) -> dict[str, Any]:
        if not isinstance(raw_data, dict):
            return {}

        metadata = raw_data.get("metadata")

        if isinstance(metadata, dict):
            return {
                **raw_data,
                **metadata,
            }

        return raw_data

    def _extract_operations(
        self,
        raw_data: dict[str, Any] | list[Any],
    ) -> list[dict[str, Any]]:
        if isinstance(raw_data, list):
            operations = raw_data

        elif isinstance(raw_data, dict):
            operations = []

            for key in self.OPERATION_LIST_KEYS:
                candidate = raw_data.get(key)

                if isinstance(candidate, list):
                    operations = candidate
                    break

            # Some exporters may return one operation object.
            if not operations and any(
                key in raw_data
                for key in self.NAME_KEYS
            ):
                operations = [raw_data]

        else:
            raise ValueError(
                "Operation contexts must be a JSON object "
                "or a JSON array."
            )

        valid_operations = [
            operation
            for operation in operations
            if isinstance(operation, dict)
        ]

        if not valid_operations:
            raise ValueError(
                "No operation contexts were found."
            )

        return valid_operations

    def _assign_numbers(
        self,
        raw_operations: list[dict[str, Any]],
    ) -> list[
        tuple[int, str | None, dict[str, Any]]
    ]:
        result = []

        for index, operation in enumerate(
            raw_operations,
            start=1,
        ):
            number = self._get_first(
                operation,
                self.NUMBER_KEYS,
                default=index,
            )

            if not isinstance(number, int):
                try:
                    number = int(number)
                except (TypeError, ValueError):
                    number = index

            operation_id = self._clean_optional_text(
                self._get_first(
                    operation,
                    self.ID_KEYS,
                )
            )

            result.append(
                (
                    number,
                    operation_id,
                    operation,
                )
            )

        return sorted(
            result,
            key=lambda item: item[0],
        )

    def _resolve_references(
        self,
        references: Any,
        operation_number_by_id: dict[str, int],
    ) -> list[int]:
        if not isinstance(references, list):
            return []

        numbers: list[int] = []

        for reference in references:
            if isinstance(reference, int):
                numbers.append(reference)
                continue

            if isinstance(reference, str):
                if reference in operation_number_by_id:
                    numbers.append(
                        operation_number_by_id[
                            reference
                        ]
                    )
                continue

            if not isinstance(reference, dict):
                continue

            explicit_number = self._first_non_empty(
                reference.get(
                    "operation_number"
                ),
                reference.get("number"),
            )

            if isinstance(explicit_number, int):
                numbers.append(explicit_number)
                continue

            reference_id = self._clean_optional_text(
                self._first_non_empty(
                    reference.get(
                        "bpmn_element_id"
                    ),
                    reference.get("id"),
                    reference.get(
                        "operation_id"
                    ),
                )
            )

            if (
                reference_id
                and reference_id
                in operation_number_by_id
            ):
                numbers.append(
                    operation_number_by_id[
                        reference_id
                    ]
                )

        return list(
            dict.fromkeys(numbers)
        )

    @staticmethod
    def _execution_mode(
        *,
        element_kind: str,
        source_type: str | None,
        actor: str | None,
    ) -> str:
        normalized_kind = element_kind.casefold()
        normalized_source = (
            source_type.casefold()
            if source_type
            else ""
        )

        if (
            normalized_kind
            in {
                "business_event",
                "event",
                "start_event",
                "end_event",
            }
            or normalized_source.endswith(
                "event"
            )
        ):
            return "event"

        if normalized_source == "servicetask":
            return "automated"

        if (
            normalized_kind == "subprocess"
            or normalized_source
            in {
                "subprocess",
                "callactivity",
            }
        ):
            return "subprocess"

        if actor:
            return "human"

        return "unspecified"

    @staticmethod
    def _event_role(
        *,
        execution_mode: str,
        source_type: str | None,
    ) -> str | None:
        if execution_mode != "event":
            return None

        normalized_source = (
            source_type.casefold()
            if source_type
            else ""
        )

        if normalized_source.endswith(
            "startevent"
        ):
            return "start"

        if normalized_source.endswith(
            "endevent"
        ):
            return "end"

        return "intermediate"

    def _determine_end_event_status(
        self,
        *,
        raw_data: dict[str, Any] | list[Any],
        operations: list[NarrativeOperation],
    ) -> str:
        validation_codes = (
            self._collect_validation_codes(
                raw_data
            )
        )

        if (
            "PROCESS_WITHOUT_END_EVENT"
            in validation_codes
        ):
            return "absent"

        if any(
            operation.event_role == "end"
            for operation in operations
        ):
            return "present"

        return "unknown"

    def _collect_validation_codes(
        self,
        value: Any,
    ) -> set[str]:
        codes: set[str] = set()

        if isinstance(value, dict):
            issue_codes = value.get(
                "validation_issue_codes"
            )

            if isinstance(issue_codes, list):
                codes.update(
                    str(code)
                    for code in issue_codes
                    if code
                )

            parser_codes = value.get(
                "parser_issue_codes"
            )

            if isinstance(parser_codes, list):
                codes.update(
                    str(code)
                    for code in parser_codes
                    if code
                )

            for child in value.values():
                codes.update(
                    self._collect_validation_codes(
                        child
                    )
                )

        elif isinstance(value, list):
            for child in value:
                codes.update(
                    self._collect_validation_codes(
                        child
                    )
                )

        return codes

    @staticmethod
    def _extract_text_list(
        values: Any,
    ) -> list[str]:
        if not isinstance(values, list):
            return []

        result: list[str] = []

        for value in values:
            if isinstance(value, str):
                text = value.strip()

            elif isinstance(value, dict):
                text = str(
                    value.get("text")
                    or value.get("name")
                    or ""
                ).strip()

            else:
                text = ""

            if text:
                result.append(text)

        return list(
            dict.fromkeys(result)
        )

    @staticmethod
    def _extract_document_names(
        values: Any,
    ) -> list[str]:
        if not isinstance(values, list):
            return []

        result: list[str] = []

        for value in values:
            if isinstance(value, str):
                name = value.strip()

            elif isinstance(value, dict):
                name = str(
                    value.get("name")
                    or value.get("label")
                    or value.get("text")
                    or ""
                ).strip()

            else:
                name = ""

            if name:
                result.append(name)

        return list(
            dict.fromkeys(result)
        )

    @staticmethod
    def _normalize_actor_name(
        name: str,
    ) -> str:
        replacements = {
            "Direction Financiére": (
                "Direction Financière"
            ),
        }

        cleaned = " ".join(
            name.split()
        ).strip()

        return replacements.get(
            cleaned,
            cleaned,
        )

    def _clean_optional_text(
        self,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = " ".join(
            str(value).split()
        ).strip()

        if not text:
            return None

        return self._normalize_actor_name(
            text
        )

    @staticmethod
    def _get_first(
        source: dict[str, Any],
        keys: tuple[str, ...],
        *,
        default: Any = None,
    ) -> Any:
        for key in keys:
            if (
                key in source
                and source[key]
                not in (
                    None,
                    "",
                )
            ):
                return source[key]

        return default

    @staticmethod
    def _first_non_empty(
        *values: Any,
    ) -> Any:
        for value in values:
            if value not in (
                None,
                "",
            ):
                return value

        return None
