"""Command-line interface for the BPMN parser."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .parser import BpmnParseError, BpmnParser


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse a BPMN XML file into a typed semantic model."
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Path to the BPMN XML file.",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional JSON output path.",
    )

    parser.add_argument(
        "--compact",
        action="store_true",
        help="Produce compact JSON.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    argument_parser = build_argument_parser()
    args = argument_parser.parse_args(argv)

    parser = BpmnParser()

    try:
        model = parser.parse_file(args.input)
    except (
        FileNotFoundError,
        BpmnParseError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    indent = None if args.compact else 2

    output = json.dumps(
        model.model_dump(
            mode="json",
            exclude_none=True,
        ),
        ensure_ascii=False,
        indent=indent,
    )

    if args.output:
        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        args.output.write_text(
            output + "\n",
            encoding="utf-8",
        )

        print(f"Written: {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())