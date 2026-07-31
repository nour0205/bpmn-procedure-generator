"""Export LLM-ready operation contexts from a BPMN file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent.context_builder import OperationContextBuilder
from bpmn.parser import BpmnParseError, BpmnParser
from pipeline.service import PipelineError
from procedure.mapper import ProcedureMapper


def select_process_id(
    bpmn_model,
    requested_process_id: str | None,
) -> str:
    """Select the modeled process, ignoring empty Bizagi wrappers."""

    if requested_process_id:
        if bpmn_model.process_by_id(requested_process_id) is None:
            raise ValueError(
                f"Unknown process ID: {requested_process_id}"
            )
        return requested_process_id

    process_ids_with_nodes = {
        node.process_id
        for node in bpmn_model.flow_nodes
    }

    candidates = [
        process
        for process in bpmn_model.processes
        if process.id in process_ids_with_nodes
    ]

    if not candidates:
        raise PipelineError(
            "No BPMN process containing flow nodes was found."
        )

    if len(candidates) > 1:
        available = ", ".join(
            f"{process.name or process.id} ({process.id})"
            for process in candidates
        )

        raise PipelineError(
            "Several modeled processes were found. "
            f"Use --process-id. Available: {available}"
        )

    return candidates[0].id


def is_technical_title(
    value: str | None,
    process_id: str,
) -> bool:
    """Return True when a title is missing or looks like a BPMN ID."""

    title = str(value or "").strip()
    normalized_process_id = str(process_id).strip()

    return (
        not title
        or title == normalized_process_id
        or title.startswith("Id_")
        or title.startswith("Process_")
    )


def resolve_process_title(
    *,
    bpmn_model,
    process_id: str,
    procedure_title: str | None,
    bpmn_path: Path,
) -> str:
    """
    Resolve a readable process title.

    Priority:
    1. procedure metadata title;
    2. BPMN process name;
    3. BPMN filename.
    """

    if not is_technical_title(
        procedure_title,
        process_id,
    ):
        return str(procedure_title).strip()

    process = bpmn_model.process_by_id(process_id)

    if (
        process is not None
        and not is_technical_title(
            process.name,
            process_id,
        )
    ):
        return str(process.name).strip()

    filename_title = bpmn_path.stem.strip()

    if filename_title:
        return filename_title

    raise ValueError(
        "Unable to determine a readable title "
        f"for BPMN process {process_id!r}."
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export operation contexts from BPMN for remote LLM inference."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Path to the BPMN file.",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output JSON path.",
    )

    parser.add_argument(
        "--process-id",
        help="Optional BPMN process ID.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)

    try:
        bpmn_model = BpmnParser().parse_file(args.input)

        process_id = select_process_id(
            bpmn_model=bpmn_model,
            requested_process_id=args.process_id,
        )

        procedure = ProcedureMapper().map_process(
            model=bpmn_model,
            process_id=process_id,
        )

        contexts = OperationContextBuilder().build_all(
            procedure
        )

        process_title = resolve_process_title(
            bpmn_model=bpmn_model,
            process_id=process_id,
            procedure_title=procedure.metadata.title,
            bpmn_path=args.input,
        )

    except (
        FileNotFoundError,
        BpmnParseError,
        PipelineError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    export_data = {
        "process_id": procedure.metadata.process_id,
        "title": process_title,
        "operation_count": len(contexts),
        "contexts": [
            context.model_dump(
                mode="json",
                exclude_none=True,
            )
            for context in contexts
        ],
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            export_data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Written: {args.output} "
        f"({len(contexts)} operation contexts)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
