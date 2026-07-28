
"""Command-line interface for the complete generation pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bpmn.parser import BpmnParseError

from .service import (
    PipelineError,
    ProcedureGenerationPipeline,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a BPMN file and generate a structured "
            "procedure draft."
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
        help="Path to the generated procedure draft JSON.",
    )

    parser.add_argument(
        "--process-id",
        help=(
            "Optional BPMN process ID. Required only when "
            "several processes contain flow nodes."
        ),
    )

    parser.add_argument(
        "--save-intermediate",
        action="store_true",
        help=(
            "Also save the BPMN model and ProcedureModel "
            "beside the draft."
        ),
    )

    return parser


def write_json(
    path: Path,
    data: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(
    argv: list[str] | None = None,
) -> int:
    argument_parser = build_argument_parser()
    args = argument_parser.parse_args(argv)

    pipeline = ProcedureGenerationPipeline()

    try:
        result = pipeline.run(
            bpmn_path=args.input,
            process_id=args.process_id,
        )
    except (
        FileNotFoundError,
        BpmnParseError,
        PipelineError,
        ValueError,
    ) as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1

    write_json(
        args.output,
        result.procedure_draft.model_dump(
            mode="json",
            exclude_none=True,
        ),
    )

    if args.save_intermediate:
        bpmn_output = args.output.with_name(
            f"{args.output.stem}_bpmn_model.json"
        )

        procedure_output = args.output.with_name(
            f"{args.output.stem}_procedure_model.json"
        )

        write_json(
            bpmn_output,
            result.bpmn_model.model_dump(
                mode="json",
                exclude_none=True,
            ),
        )

        write_json(
            procedure_output,
            result.procedure_model.model_dump(
                mode="json",
                exclude_none=True,
            ),
        )

        print(f"Written: {bpmn_output}")
        print(f"Written: {procedure_output}")

    print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())