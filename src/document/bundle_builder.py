
"""Merge deterministic process data with LLM-generated descriptions."""

from __future__ import annotations

from procedure.models import ProcedureModel

from .loader import GeneratedProcedure
from .models import (
    DocumentActor,
    DocumentBranch,
    DocumentBundle,
    DocumentBusinessDocument,
    DocumentBusinessRule,
    DocumentMetadata,
    DocumentNote,
    DocumentOperation,
    DocumentOperationKind,
    DocumentValidationSummary,
    ProcedureDocumentData,
    SpecificationDocumentData,
)
from .text_normalization import (
    normalize_branch_label,
    normalize_french_business_text,
    symbolic_delay_labels,
)


class DocumentBundleBuildError(ValueError):
    """Raised when the deterministic and generated models are inconsistent."""


class DocumentBundleBuilder:
    """Build the shared document model."""

    def build(
        self,
        procedure: ProcedureModel,
        generated: GeneratedProcedure,
    ) -> DocumentBundle:
        if procedure.metadata.process_id != generated.process_id:
            raise DocumentBundleBuildError(
                "The ProcedureModel and generated procedure use "
                "different process IDs."
            )

        generated_by_id = {
            operation.bpmn_element_id: operation
            for operation in generated.operations
        }

        deterministic_ids = {
            operation.bpmn_element_id
            for operation in procedure.operations
        }

        generated_ids = set(generated_by_id)

        missing_ids = deterministic_ids - generated_ids
        extra_ids = generated_ids - deterministic_ids

        if missing_ids:
            raise DocumentBundleBuildError(
                "Generated descriptions are missing for: "
                + ", ".join(sorted(missing_ids))
            )

        if extra_ids:
            raise DocumentBundleBuildError(
                "Generated descriptions contain unknown operations: "
                + ", ".join(sorted(extra_ids))
            )

        self._validate_enriched_contract(
            procedure=procedure,
            generated=generated,
            generated_by_id=generated_by_id,
        )

        actors = self._build_actors(procedure)
        documents = self._build_documents(procedure)
        operations = self._build_operations(
            procedure=procedure,
            generated_by_id=generated_by_id,
        )

        business_rules = self._build_business_rules(
            operations=operations,
        )

        subprocess_ids = [
            operation.bpmn_element_id
            for operation in operations
            if operation.element_kind
            == DocumentOperationKind.SUBPROCESS
        ]

        business_event_ids = [
            operation.bpmn_element_id
            for operation in operations
            if operation.element_kind
            == DocumentOperationKind.BUSINESS_EVENT
        ]

        decision_gateway_ids = sorted(
            {
                branch.gateway_id
                for operation in operations
                for branch in operation.branches
            }
        )

        metadata = DocumentMetadata(
            process_id=procedure.metadata.process_id,
            title=normalize_french_business_text(
                generated.title
            ),
            source_bpmn_path=procedure.metadata.source_path,
        )

        validation = DocumentValidationSummary(
            parser_is_valid=procedure.validation.is_valid,
            parser_error_count=procedure.validation.error_count,
            parser_warning_count=procedure.validation.warning_count,
            parser_issue_codes=procedure.validation.issue_codes,
            generation_warnings=generated.generation_warnings,
            generation_operations_requiring_validation=(
                generated.operations_requiring_validation
            ),
            generation_placeholder_count=generated.placeholder_count,
            generation_missing_note_count=generated.missing_note_count,
        )

        first_operation_name = (
            normalize_french_business_text(
                operations[0].raw_name
            )
            if operations
            else metadata.title
        )
        last_operation_name = (
            normalize_french_business_text(
                operations[-1].raw_name
            )
            if operations
            else metadata.title
        )

        procedure_data = ProcedureDocumentData(
            purpose=(
                "Cette procédure décrit le déroulement du processus "
                f"« {metadata.title} », depuis « {first_operation_name} » "
                f"jusqu’à « {last_operation_name} ». Elle précise les "
                "responsabilités, les décisions et les règles associées."
            ),
            operations=operations,
            documents=documents,
            business_rules=business_rules,
        )

        specification_data = SpecificationDocumentData(
            actors=actors,
            operations=operations,
            documents=documents,
            subprocess_operation_ids=subprocess_ids,
            business_event_operation_ids=business_event_ids,
            decision_gateway_ids=decision_gateway_ids,
            unresolved_points=self._build_unresolved_points(
                operations=operations,
                validation=validation,
            ),
        )

        return DocumentBundle(
            metadata=metadata,
            actors=actors,
            documents=documents,
            operations=operations,
            validation=validation,
            procedure=procedure_data,
            specification=specification_data,
        )

    @classmethod
    def _validate_enriched_contract(
        cls,
        *,
        procedure: ProcedureModel,
        generated: GeneratedProcedure,
        generated_by_id: dict,
    ) -> None:
        """Validate duplicated deterministic metadata from Kaggle.

        The enriched JSON intentionally repeats structural BPMN facts.  Those
        fields are not trusted as a second source of truth: when present, they
        must match the local deterministic ProcedureModel exactly.  This turns
        the additional metadata into an end-to-end integrity check instead of
        silently discarding it.
        """

        document_name_by_id = {
            document.id: document.name
            for document in procedure.documents
        }
        note_by_id = {
            note.id: note.text
            for note in procedure.notes
        }
        operation_by_id = {
            operation.bpmn_element_id: operation
            for operation in procedure.operations
        }

        for source in procedure.operations:
            mirror = generated_by_id[source.bpmn_element_id]
            mismatches: list[str] = []

            cls._compare_optional_mirror(
                mismatches,
                mirror,
                "raw_name",
                source.raw_name,
            )
            cls._compare_optional_mirror(
                mismatches,
                mirror,
                "actor_name",
                source.actor_name,
            )
            cls._compare_optional_mirror(
                mismatches,
                mirror,
                "element_kind",
                source.element_kind.value,
            )
            cls._compare_optional_mirror(
                mismatches,
                mirror,
                "source_type",
                source.source_type,
            )

            if mirror.operation_number != source.number:
                mismatches.append(
                    "operation_number "
                    f"(generated={mirror.operation_number!r}, "
                    f"deterministic={source.number!r})"
                )

            source_execution_mode = getattr(
                source,
                "execution_mode",
                None,
            )
            if source_execution_mode is not None:
                source_execution_mode = getattr(
                    source_execution_mode,
                    "value",
                    source_execution_mode,
                )
                cls._compare_optional_mirror(
                    mismatches,
                    mirror,
                    "execution_mode",
                    source_execution_mode,
                )

            source_event_role = getattr(source, "event_role", None)
            if source_event_role is not None:
                source_event_role = getattr(
                    source_event_role,
                    "value",
                    source_event_role,
                )
                cls._compare_optional_mirror(
                    mismatches,
                    mirror,
                    "event_role",
                    source_event_role,
                )

            if "previous_operations" in mirror.model_fields_set:
                generated_previous = [
                    item.id for item in mirror.previous_operations
                ]
                if generated_previous != source.previous_operation_ids:
                    mismatches.append(
                        "previous_operations IDs do not match"
                    )

            if "next_operations" in mirror.model_fields_set:
                generated_next = [
                    item.id for item in mirror.next_operations
                ]
                if generated_next != source.next_operation_ids:
                    mismatches.append(
                        "next_operations IDs do not match"
                    )

            if "branches" in mirror.model_fields_set:
                generated_branches = {
                    (
                        branch.gateway_id,
                        branch.label,
                        branch.condition,
                        branch.is_default,
                        branch.is_loop_back,
                        branch.target_element_id,
                    )
                    for branch in mirror.branches
                }
                deterministic_branches = {
                    (
                        branch.gateway_id,
                        branch.label,
                        branch.condition,
                        branch.is_default,
                        branch.is_loop_back,
                        branch.target_element_id,
                    )
                    for branch in source.branches
                }
                if generated_branches != deterministic_branches:
                    mismatches.append("branches do not match")

            expected_input_names = [
                document_name_by_id[document_id]
                for document_id in source.input_document_ids
                if document_id in document_name_by_id
            ]
            if (
                "input_document_names" in mirror.model_fields_set
                and mirror.input_document_names != expected_input_names
            ):
                mismatches.append("input_document_names do not match")

            expected_output_names = [
                document_name_by_id[document_id]
                for document_id in source.output_document_ids
                if document_id in document_name_by_id
            ]
            if (
                "output_document_names" in mirror.model_fields_set
                and mirror.output_document_names != expected_output_names
            ):
                mismatches.append("output_document_names do not match")

            if "associated_notes" in mirror.model_fields_set:
                expected_notes = {
                    note_id: note_by_id[note_id]
                    for note_id in source.note_ids
                    if note_id in note_by_id
                }
                generated_notes = {
                    note.id: note.text
                    for note in mirror.associated_notes
                }
                if generated_notes != expected_notes:
                    mismatches.append("associated_notes do not match")

            if mismatches:
                raise DocumentBundleBuildError(
                    "Generated metadata is inconsistent for operation "
                    f"{source.number} ({source.bpmn_element_id}): "
                    + "; ".join(mismatches)
                )

        if "decisions" in generated.model_fields_set:
            for decision in generated.decisions:
                source = operation_by_id.get(
                    decision.source_bpmn_element_id
                )
                if source is None:
                    raise DocumentBundleBuildError(
                        "Generated decision has an unknown source operation: "
                        f"{decision.source_bpmn_element_id}"
                    )

                if source.number != decision.source_operation_number:
                    raise DocumentBundleBuildError(
                        "Generated decision source number does not match "
                        f"{decision.source_bpmn_element_id}."
                    )

                expected_targets = {
                    branch.target_element_id
                    for branch in source.branches
                    if branch.gateway_id == decision.gateway_id
                }
                generated_targets = {
                    branch.target_element_id
                    for branch in decision.branches
                }
                if generated_targets != expected_targets:
                    raise DocumentBundleBuildError(
                        "Generated decision branches do not match gateway "
                        f"{decision.gateway_id}."
                    )

    @staticmethod
    def _compare_optional_mirror(
        mismatches: list[str],
        mirror,
        field_name: str,
        deterministic_value,
    ) -> None:
        """Compare a mirror field only when the JSON explicitly contains it."""

        if field_name not in mirror.model_fields_set:
            return

        generated_value = getattr(mirror, field_name)
        if generated_value != deterministic_value:
            mismatches.append(
                f"{field_name} "
                f"(generated={generated_value!r}, "
                f"deterministic={deterministic_value!r})"
            )

    @staticmethod
    def _build_actors(
        procedure: ProcedureModel,
    ) -> list[DocumentActor]:
        operation_ids_by_actor: dict[str, list[str]] = {}

        for operation in procedure.operations:
            if not operation.actor_id:
                continue

            operation_ids_by_actor.setdefault(
                operation.actor_id,
                [],
            ).append(operation.bpmn_element_id)

        return [
            DocumentActor(
                id=actor.id,
                name=normalize_french_business_text(
                    actor.name
                ),
                source_type=actor.source_type,
                operation_ids=operation_ids_by_actor.get(
                    actor.id,
                    [],
                ),
            )
            for actor in procedure.actors
        ]

    @staticmethod
    def _build_documents(
        procedure: ProcedureModel,
    ) -> list[DocumentBusinessDocument]:
        return [
            DocumentBusinessDocument(
                id=document.id,
                name=normalize_french_business_text(
                    document.name
                ),
                source_type=document.source_type,
                produced_by_operation_ids=(
                    document.produced_by_operation_ids
                ),
                consumed_by_operation_ids=(
                    document.consumed_by_operation_ids
                ),
            )
            for document in procedure.documents
        ]

    @staticmethod
    def _build_operations(
        procedure: ProcedureModel,
        generated_by_id: dict,
    ) -> list[DocumentOperation]:
        result: list[DocumentOperation] = []

        operation_name_by_id = {
            operation.bpmn_element_id: operation.raw_name
            for operation in procedure.operations
        }

        document_by_id = {
            document.id: document
            for document in procedure.documents
        }

        note_by_id = {
            note.id: note
            for note in procedure.notes
        }

        for source in procedure.operations:
            generated = generated_by_id[source.bpmn_element_id]

            incorporated_note_ids = set(
                generated.incorporated_note_ids
            )

            source_notes = [
                note_by_id[note_id]
                for note_id in source.note_ids
                if note_id in note_by_id
            ]

            notes = [
                DocumentNote(
                    id=note.id,
                    text=normalize_french_business_text(
                        note.text
                    ),
                    incorporated_in_description=(
                        note.id in incorporated_note_ids
                    ),
                )
                for note in source_notes
            ]

            input_document_names = [
                normalize_french_business_text(
                    document_by_id[document_id].name
                )
                for document_id in source.input_document_ids
                if document_id in document_by_id
            ]

            output_document_names = [
                normalize_french_business_text(
                    document_by_id[document_id].name
                )
                for document_id in source.output_document_ids
                if document_id in document_by_id
            ]

            branches = [
                DocumentBranch(
                    gateway_id=branch.gateway_id,
                    gateway_name=(
                        normalize_french_business_text(
                            branch.gateway_name
                        )
                        or None
                    ),
                    label=normalize_branch_label(
                        normalize_french_business_text(
                            branch.label
                        )
                    ),
                    condition=(
                        normalize_french_business_text(
                            branch.condition
                        )
                        or None
                    ),
                    is_default=branch.is_default,
                    is_loop_back=branch.is_loop_back,
                    target_operation_id=branch.target_element_id,
                    target_operation_name=(
                        normalize_french_business_text(
                            operation_name_by_id.get(
                                branch.target_element_id
                            )
                        )
                        or None
                    ),
                )
                for branch in source.branches
            ]

            result.append(
                DocumentOperation(
                    number=source.number,
                    bpmn_element_id=source.bpmn_element_id,
                    raw_name=source.raw_name,
                    description=normalize_french_business_text(
                        generated.description
                    ),
                    actor_id=source.actor_id,
                    actor_name=(
                        normalize_french_business_text(
                            source.actor_name
                        )
                        or None
                    ),
                    raw_actor_name=source.raw_actor_name,
                    element_kind=DocumentOperationKind(
                        source.element_kind.value
                    ),
                    source_type=source.source_type,
                    execution_mode=(
                        generated.execution_mode
                        or getattr(source, "execution_mode", None)
                    ),
                    event_role=(
                        generated.event_role
                        or getattr(source, "event_role", None)
                    ),
                    previous_operation_ids=source.previous_operation_ids,
                    next_operation_ids=source.next_operation_ids,
                    input_document_names=input_document_names,
                    output_document_names=output_document_names,
                    notes=notes,
                    branches=branches,
                    is_common_continuation=(
                        source.is_common_continuation
                    ),
                    convergence_gateway_ids=list(
                        source.convergence_gateway_ids
                    ),
                    confidence=generated.confidence,
                    requires_validation=generated.requires_validation,
                    warnings=generated.warnings,
                    validation_issue_codes=(
                        generated.validation_issue_codes
                    ),
                )
            )

        return result

    @staticmethod
    def _normalize_business_rule_text(
        text: str,
    ) -> str:
        """Clean BPMN annotation text without changing its meaning."""

        normalized = normalize_french_business_text(
            text.replace("\n", " ")
        )

        normalized = normalized.rstrip(
            " ,.;:"
        )

        if not normalized:
            return ""

        normalized = (
            normalized[0].upper()
            + normalized[1:]
        )

        return normalized + "."

    @staticmethod
    def _build_business_rules(
        operations: list[DocumentOperation],
    ) -> list[DocumentBusinessRule]:
        """
        Create one business rule for every BPMN annotation.

        All original notes are preserved, including notes already incorporated
        into the generated operation description.
        """

        rules: list[DocumentBusinessRule] = []
        seen_note_ids: set[str] = set()

        for operation in operations:
            for note in operation.notes:
                note_text = note.text.strip()

                if not note_text:
                    continue

                if note.id in seen_note_ids:
                    continue

                seen_note_ids.add(
                    note.id
                )

                normalized_text = (
                    DocumentBundleBuilder
                    ._normalize_business_rule_text(
                        note_text
                    )
                )

                if not normalized_text:
                    continue

                rules.append(
                    DocumentBusinessRule(
                        operation_number=operation.number,
                        text=normalized_text,
                        source_note_id=note.id,
                    )
                )

        return rules

    @staticmethod
    def _build_unresolved_points(
        operations: list[DocumentOperation],
        validation: DocumentValidationSummary,
    ) -> list[str]:
        unresolved: list[str] = []

        for operation in operations:
            display_name = normalize_french_business_text(
                operation.raw_name
            )

            for delay_label in symbolic_delay_labels(
                operation.raw_name
            ):
                unresolved.append(
                    f"Opération {operation.number} « {display_name} » : "
                    f"la valeur du délai {delay_label} est à confirmer "
                    "par le métier."
                )

        # Technical generation warnings remain available in the bundle's
        # validation section. They must not be exposed as business questions
        # in the procedure or specification documents.
        return list(dict.fromkeys(unresolved))
