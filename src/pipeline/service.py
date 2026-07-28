
"""End-to-end BPMN procedure generation pipeline."""

from __future__ import annotations

from pathlib import Path

from agent.llm import (
    DeterministicOperationGenerator,
    OperationGenerator,
)
from agent.models import ProcedureDraft
from agent.orchestrator import ProcedureAgent
from bpmn.models import BpmnModel
from bpmn.parser import BpmnParser
from procedure.mapper import ProcedureMapper
from procedure.models import ProcedureModel


class PipelineError(Exception):
    """Raised when the procedure-generation pipeline cannot continue."""


class ProcedureGenerationResult:
    """Contains every important output produced by the pipeline."""

    def __init__(
        self,
        bpmn_model: BpmnModel,
        procedure_model: ProcedureModel,
        procedure_draft: ProcedureDraft,
    ) -> None:
        self.bpmn_model = bpmn_model
        self.procedure_model = procedure_model
        self.procedure_draft = procedure_draft


class ProcedureGenerationPipeline:
    """Run parsing, mapping and draft generation in one service."""

    def __init__(
        self,
        parser: BpmnParser | None = None,
        mapper: ProcedureMapper | None = None,
        generator: OperationGenerator | None = None,
    ) -> None:
        self.parser = parser or BpmnParser()
        self.mapper = mapper or ProcedureMapper()

        self.agent = ProcedureAgent(
            generator=(
                generator
                or DeterministicOperationGenerator()
            )
        )

    def run(
        self,
        bpmn_path: str | Path,
        process_id: str | None = None,
    ) -> ProcedureGenerationResult:
        """Generate a procedure draft from a BPMN file."""

        bpmn_model = self.parser.parse_file(bpmn_path)

        selected_process_id = (
            process_id
            or self._select_process_id(bpmn_model)
        )

        procedure_model = self.mapper.map_process(
            model=bpmn_model,
            process_id=selected_process_id,
        )

        procedure_draft = self.agent.generate(
            procedure_model
        )

        return ProcedureGenerationResult(
            bpmn_model=bpmn_model,
            procedure_model=procedure_model,
            procedure_draft=procedure_draft,
        )

    @staticmethod
    def _select_process_id(
        model: BpmnModel,
    ) -> str:
        """
        Select the only process containing flow nodes.

        Empty Bizagi wrapper processes are ignored.
        """

        process_ids_with_nodes = {
            node.process_id
            for node in model.flow_nodes
        }

        candidate_processes = [
            process
            for process in model.processes
            if process.id in process_ids_with_nodes
        ]

        if not candidate_processes:
            raise PipelineError(
                "No BPMN process containing flow nodes was found."
            )

        if len(candidate_processes) > 1:
            available = ", ".join(
                (
                    f"{process.name or 'Unnamed process'} "
                    f"({process.id})"
                )
                for process in candidate_processes
            )

            raise PipelineError(
                "Several BPMN processes contain flow nodes. "
                "Provide process_id explicitly. "
                f"Available processes: {available}"
            )

        return candidate_processes[0].id