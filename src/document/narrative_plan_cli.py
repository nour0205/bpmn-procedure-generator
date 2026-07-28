"""Export an explicit narrative plan from narrative context."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .narrative_models import NarrativeContext
from .narrative_plan_builder import (
    NarrativePlanBuilder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build an explicit narrative plan "
            "from narrative_context.json."
        )
    )

    parser.add_argument(
        "context_path",
        type=Path,
        help="Path to narrative_context.json",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path for narrative_plan.json",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        raw_data = json.loads(
            args.context_path.read_text(
                encoding="utf-8"
            )
        )

        context = NarrativeContext.model_validate(
            raw_data
        )

        plan = NarrativePlanBuilder().build(
            context
        )

        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        args.output.write_text(
            json.dumps(
                plan.model_dump(
                    mode="json"
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    except FileNotFoundError as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1

    except PermissionError as exc:
        print(
            f"Error: cannot access file: {exc}",
            file=sys.stderr,
        )
        return 1

    except (
        json.JSONDecodeError,
        ValidationError,
        ValueError,
        TypeError,
    ) as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Written: {args.output}"
    )

    print(
        "Process:",
        plan.process_title,
    )

    print(
        "Operations:",
        len(plan.operations),
    )

    print(
        "Decisions:",
        len(plan.decisions),
    )

    print(
        "Convergences:",
        len(plan.convergences),
    )

    print(
        "Writing blocks:",
        len(plan.writing_blocks),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
