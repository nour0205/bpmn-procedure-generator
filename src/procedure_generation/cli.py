"""Local deterministic CLI for testing the procedure pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from procedure_generation.config import (
    ProcedureGenerationConfig,
)
from procedure_generation.runner import (
    run_procedure_generation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic BPMN procedure "
            "without loading an LLM."
        )
    )
    parser.add_argument(
        "operation_contexts",
        type=Path,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--title",
        default=None,
        help=(
            "Optional readable process-title override."
        ),
    )
    return parser


def main(
    argv: list[str] | None = None,
) -> int:
    args = build_parser().parse_args(
        argv
    )

    try:
        result = run_procedure_generation(
            operation_contexts_path=(
                args.operation_contexts
            ),
            output_dir=(
                args.output_dir
            ),
            config=ProcedureGenerationConfig(
                use_model=False,
                title_override=args.title,
            ),
        )
    except (
        FileNotFoundError,
        PermissionError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as error:
        print(
            f"Error: {error}",
            file=sys.stderr,
        )
        return 1

    print(
        "Written:",
        result.generated_procedure_path,
    )
    print(
        "Written:",
        result.validation_report_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
