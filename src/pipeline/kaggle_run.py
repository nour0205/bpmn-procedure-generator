"""CLI for automatic Kaggle upload, execution and output download."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .kaggle_client import (
    KaggleAutomationError,
    KaggleGenerationService,
    KaggleSettings,
    username_from_environment,
)
from .paths import AutomationPaths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Upload prepared inputs, execute the combined Kaggle worker "
            "and download its outputs."
        )
    )
    parser.add_argument("--slug", required=True)
    parser.add_argument("--kaggle-username", default=None)
    parser.add_argument(
        "--dataset-slug",
        default="bpmn-generation-inputs",
    )
    parser.add_argument(
        "--kernel-slug",
        default="qwen-bpmn-combined-worker",
    )
    parser.add_argument(
        "--notebook",
        type=Path,
        default=Path(
            "notebooks/qwen-bpmn-combined-worker.ipynb"
        ),
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--timeout-minutes", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        username = username_from_environment(args.kaggle_username)
        paths = AutomationPaths.build(
            project_root=args.project_root,
            output_root=args.output_root,
            process_slug=args.slug,
        )
        settings = KaggleSettings(
            username=username,
            dataset_slug=args.dataset_slug,
            kernel_slug=args.kernel_slug,
            poll_seconds=max(5, args.poll_seconds),
            timeout_seconds=max(60, args.timeout_minutes * 60),
        )
        service = KaggleGenerationService(
            paths=paths,
            settings=settings,
            notebook_path=args.notebook,
        )
        manifest = service.execute(dry_run=args.dry_run)
    except (
        FileNotFoundError,
        ValueError,
        KaggleAutomationError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Run ID: {manifest.run_id}")
    if not args.dry_run:
        print(f"Downloaded outputs: {paths.download_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
