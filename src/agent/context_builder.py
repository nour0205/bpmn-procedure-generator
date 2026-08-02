"""Build compact operation contexts from a ProcedureModel."""

from __future__ import annotations

from procedure.models import (
    ProcedureDocument,
    ProcedureModel,
    ProcedureOperation,
)

from .models import (
    ContextBranch,
    ContextDocument,
    ContextNeighbour,
    ContextNote,
    OperationContext,
)


class OperationContextBuilder:
    """Convert procedure operations into LLM-ready contexts."""

    def build_all(
        self,
        procedure: ProcedureModel,
    ) -> list[OperationContext]:
        return [
            self.build_one(
                procedure=procedure,
                operation=operation,
            )
            for operation in procedure.operations
        ]

    def build_one(
        self,
        procedure: ProcedureModel,
        operation: ProcedureOperation,
    ) -> OperationContext:
        operations_by_id = {
            item.bpmn_element_id: item
            for item in procedure.operations
        }

        documents_by_id = {
            item.id: item
            for item in procedure.documents
        }

        notes_by_id = {
            item.id: item
            for item in procedure.notes
        }

        previous_operations = [
            self._build_neighbour(
                operations_by_id[operation_id]
            )
            for operation_id in operation.previous_operation_ids
            if operation_id in operations_by_id
        ]

        next_operations = [
            self._build_neighbour(
                operations_by_id[operation_id]
            )
            for operation_id in operation.next_operation_ids
            if operation_id in operations_by_id
        ]

        input_documents = [
            self._build_document(
                documents_by_id[document_id],
                direction="input",
            )
            for document_id in operation.input_document_ids
            if document_id in documents_by_id
        ]

        output_documents = [
            self._build_document(
                documents_by_id[document_id],
                direction="output",
            )
            for document_id in operation.output_document_ids
            if document_id in documents_by_id
        ]

        notes = [
            ContextNote(
                id=notes_by_id[note_id].id,
                text=notes_by_id[note_id].text,
            )
            for note_id in operation.note_ids
            if note_id in notes_by_id
        ]

        branches = [
            ContextBranch(
                gateway_id=branch.gateway_id,
                gateway_name=branch.gateway_name,
                label=branch.label,
                condition=branch.condition,
                is_default=branch.is_default,
                is_loop_back=branch.is_loop_back,
                target_element_id=branch.target_element_id,
                target_name=(
                    operations_by_id[
                        branch.target_element_id
                    ].raw_name
                    if branch.target_element_id
                    in operations_by_id
                    else None
                ),
            )
            for branch in operation.branches
        ]

        return OperationContext(
            operation_number=operation.number,
            bpmn_element_id=operation.bpmn_element_id,
            raw_name=operation.raw_name,
            actor_name=operation.actor_name,
            element_kind=operation.element_kind.value,
            source_type=operation.source_type,
            previous_operations=previous_operations,
            next_operations=next_operations,
            input_documents=input_documents,
            output_documents=output_documents,
            notes=notes,
            branches=branches,
            order_ambiguous=operation.order_ambiguous,
            validation_issue_codes=(
                procedure.validation.issue_codes
            ),
        )

    @staticmethod
    def _build_neighbour(
        operation: ProcedureOperation,
    ) -> ContextNeighbour:
        return ContextNeighbour(
            id=operation.bpmn_element_id,
            name=operation.raw_name,
            actor_name=operation.actor_name,
            element_kind=operation.element_kind.value,
        )

    @staticmethod
    def _build_document(
        document: ProcedureDocument,
        direction: str,
    ) -> ContextDocument:
        return ContextDocument(
            id=document.id,
            name=document.name,
            direction=direction,
        )