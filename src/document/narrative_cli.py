"""Export narrative context from deterministic operation contexts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .narrative_context import NarrativeContextBuilder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build narrative context JSON directly "
            "from deterministic operation contexts."
        )
    )

    parser.add_argument(
        "contexts_path",
        type=Path,
        help="Path to operation_contexts.json",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path for narrative_context.json",
    )

    parser.add_argument(
        "--process-id",
        type=str,
        default=None,
        help=(
            "Optional process identifier used when it "
            "is absent from operation_contexts.json."
        ),
    )

    parser.add_argument(
        "--process-title",
        type=str,
        default=None,
        help=(
            "Optional process title used when it "
            "is absent from operation_contexts.json."
        ),
    )

    return parser


def default_process_name(
    contexts_path: Path,
) -> str:
    """
    Derive a readable fallback from the evaluation-folder name.

    Example:
    output/suivi_commandes/parser/operation_contexts.json
    becomes 'Suivi Commandes'.
    """

    try:
        folder_name = (
            contexts_path
            .resolve()
            .parent
            .parent
            .name
        )

    except (OSError, RuntimeError):
        folder_name = contexts_path.stem

    readable_name = (
        folder_name
        .replace("_", " ")
        .replace("-", " ")
        .strip()
    )

    if not readable_name:
        return "Processus"

    return readable_name.title()


def main() -> int:
    args = build_parser().parse_args()

    try:
        raw_data = json.loads(
            args.contexts_path.read_text(
                encoding="utf-8"
            )
        )

        fallback_id = (
            args.process_id
            or args.contexts_path.parent.parent.name
            or args.contexts_path.stem
        )

        context = NarrativeContextBuilder().build(
            raw_data,
            default_process_id=fallback_id,
            default_process_title=default_process_name(
                args.contexts_path
            ),
            process_title_override=args.process_title,
        )

        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        args.output.write_text(
            json.dumps(
                context.model_dump(
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
        context.process_title,
    )

    print(
        "Operations:",
        len(context.operations),
    )

    print(
        "End event:",
        context.end_event_status,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
