"""Local deterministic CLI for testing the narrative pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from narrative_generation.config import (
    NarrativeGenerationConfig,
)
from narrative_generation.runner import (
    run_narrative_generation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic BPMN narrative without "
            "loading an LLM. Intended for local validation."
        )
    )
    parser.add_argument(
        "narrative_plan",
        type=Path,
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
    return parser


def main(
    argv: list[str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)

    try:
        result = run_narrative_generation(
            narrative_plan_path=(
                args.narrative_plan
            ),
            operation_contexts_path=(
                args.operation_contexts
            ),
            output_dir=args.output_dir,
            config=NarrativeGenerationConfig(
                use_model=False
            ),
        )
    except (
        FileNotFoundError,
        PermissionError,
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
        result.generated_narrative_path,
    )
    print(
        "Written:",
        result.validation_report_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
