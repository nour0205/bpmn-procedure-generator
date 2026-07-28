"""Generate a procedure-oriented JSON file from BPMN."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bpmn.parser import BpmnParseError, BpmnParser

from .mapper import ProcedureMapper


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert BPMN into a procedure-oriented JSON model."
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
        help="Path to the generated procedure JSON.",
    )

    parser.add_argument(
        "--process-id",
        help="Specific process ID to map.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    argument_parser = build_argument_parser()
    args = argument_parser.parse_args(argv)

    try:
        bpmn_model = BpmnParser().parse_file(args.input)
    except (
        FileNotFoundError,
        BpmnParseError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    process_id = args.process_id

    if process_id is None:
        internal_processes = [
            process
            for process in bpmn_model.processes
            if any(
                node.process_id == process.id
                for node in bpmn_model.flow_nodes
            )
        ]

        if len(internal_processes) != 1:
            print(
                "Error: Multiple BPMN processes were found. "
                "Provide --process-id.",
                file=sys.stderr,
            )
            return 1

        process_id = internal_processes[0].id

    procedure = ProcedureMapper().map_process(
        model=bpmn_model,
        process_id=process_id,
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            procedure.model_dump(
                mode="json",
                exclude_none=True,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())