"""Prepare deterministic BPMN inputs for the remote Kaggle worker."""

from __future__ import annotations

import argparse
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent.context_builder import OperationContextBuilder
from agent.export_contexts import resolve_process_title, select_process_id
from bpmn.parser import BpmnParseError, BpmnParser
from document.narrative_context import NarrativeContextBuilder
from document.narrative_plan_builder import NarrativePlanBuilder
from procedure.mapper import ProcedureMapper

from .io import copy_file, write_json
from .models import GenerationMode, RunManifest
from .paths import AutomationPaths
from .service import PipelineError

DEFAULT_MODEL_NAME = "Qwen/Qwen3-8B"


class PreparationError(RuntimeError):
    """Raised when local deterministic preparation cannot finish."""


def _git_value(project_root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    value = completed.stdout.strip()
    return value or None


def _new_run_id(process_slug: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    suffix = uuid.uuid4().hex[:8]
    return f"{process_slug}-{timestamp}-{suffix}"


def _expected_outputs(mode: GenerationMode) -> list[str]:
    outputs = ["run_result.json"]

    if mode in {"procedure", "both"}:
        outputs.extend(
            [
                "generated_procedure.json",
                "procedure_validation_report.json",
                "procedure_preview.txt",
            ]
        )

    if mode in {"narrative", "both"}:
        outputs.extend(
            [
                "generated_narrative.json",
                "narrative_validation_report.json",
                "narrative_preview.txt",
            ]
        )

    return outputs


def prepare_run(
    *,
    bpmn_path: str | Path,
    process_slug: str,
    mode: GenerationMode = "both",
    project_root: str | Path = ".",
    output_root: str | Path = "output",
    process_id: str | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
    notebook_filename: str = (
        "qwen-bpmn-combined-worker.ipynb"
    ),
    allow_dirty: bool = False,
) -> RunManifest:
    """Parse one BPMN and write all deterministic remote inputs."""

    paths = AutomationPaths.build(
        project_root=project_root,
        output_root=output_root,
        process_slug=process_slug,
    )
    paths.ensure_base_directories()
    paths.reset_directory(paths.input_dir)

    git_commit = _git_value(paths.project_root, "rev-parse", "HEAD")
    git_branch = _git_value(
        paths.project_root,
        "rev-parse",
        "--abbrev-ref",
        "HEAD",
    )
    git_status = _git_value(
        paths.project_root,
        "status",
        "--porcelain",
    )
    git_dirty = bool(git_status)

    if git_dirty and not allow_dirty:
        raise PreparationError(
            "The Git working tree contains uncommitted changes. "
            "Commit and push them before remote execution, or use "
            "--allow-dirty only for a deliberate diagnostic run."
        )

    source_bpmn = Path(bpmn_path)
    if not source_bpmn.is_absolute():
        source_bpmn = paths.project_root / source_bpmn
    source_bpmn = source_bpmn.resolve()

    try:
        bpmn_model = BpmnParser().parse_file(source_bpmn)
        selected_process_id = select_process_id(
            bpmn_model=bpmn_model,
            requested_process_id=process_id,
        )
        procedure_model = ProcedureMapper().map_process(
            model=bpmn_model,
            process_id=selected_process_id,
        )
        contexts = OperationContextBuilder().build_all(
            procedure_model
        )
        process_title = resolve_process_title(
            bpmn_model=bpmn_model,
            process_id=selected_process_id,
            procedure_title=procedure_model.metadata.title,
            bpmn_path=source_bpmn,
        )
    except (
        FileNotFoundError,
        BpmnParseError,
        PipelineError,
        ValueError,
    ) as exc:
        raise PreparationError(str(exc)) from exc

    operation_contexts = {
        "process_id": procedure_model.metadata.process_id,
        "title": process_title,
        "operation_count": len(contexts),
        "contexts": [
            context.model_dump(mode="json", exclude_none=True)
            for context in contexts
        ],
    }

    bpmn_model_path = paths.parser_dir / "bpmn_model.json"
    procedure_model_path = paths.parser_dir / "procedure_model.json"
    operation_contexts_path = (
        paths.parser_dir / "operation_contexts.json"
    )

    write_json(
        bpmn_model_path,
        bpmn_model.model_dump(mode="json", exclude_none=True),
    )
    write_json(
        procedure_model_path,
        procedure_model.model_dump(mode="json", exclude_none=True),
    )
    write_json(operation_contexts_path, operation_contexts)

    if mode in {"narrative", "both"}:
        narrative_context = NarrativeContextBuilder().build(
            operation_contexts,
            default_process_id=selected_process_id,
            default_process_title=process_title,
        )
        narrative_plan = NarrativePlanBuilder().build(
            narrative_context
        )

        narrative_context_path = (
            paths.parser_dir / "narrative_context.json"
        )
        narrative_plan_path = (
            paths.parser_dir / "narrative_plan.json"
        )

        write_json(
            narrative_context_path,
            narrative_context.model_dump(mode="json"),
        )
        write_json(
            narrative_plan_path,
            narrative_plan.model_dump(mode="json"),
        )
        copy_file(
            narrative_plan_path,
            paths.input_dir / "narrative_plan.json",
        )

    copy_file(
        operation_contexts_path,
        paths.input_dir / "operation_contexts.json",
    )

    manifest = RunManifest(
        run_id=_new_run_id(process_slug),
        created_at_utc=datetime.now(timezone.utc),
        process_slug=process_slug,
        process_id=selected_process_id,
        process_title=process_title,
        bpmn_filename=source_bpmn.name,
        bpmn_path=str(source_bpmn),
        generation_mode=mode,
        model_name=model_name,
        git_commit=git_commit,
        git_branch=git_branch,
        git_dirty=git_dirty,
        notebook_filename=notebook_filename,
        expected_outputs=_expected_outputs(mode),
    )

    manifest_payload = manifest.model_dump(mode="json")
    write_json(paths.manifest_path, manifest_payload)
    write_json(paths.input_manifest_path, manifest_payload)

    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare deterministic BPMN inputs for the combined "
            "Kaggle generation worker."
        )
    )
    parser.add_argument("bpmn", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument(
        "--mode",
        choices=("procedure", "narrative", "both"),
        default="both",
    )
    parser.add_argument("--process-id", default=None)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--allow-dirty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        manifest = prepare_run(
            bpmn_path=args.bpmn,
            process_slug=args.slug,
            mode=args.mode,
            project_root=args.project_root,
            output_root=args.output_root,
            process_id=args.process_id,
            model_name=args.model_name,
            allow_dirty=args.allow_dirty,
        )
    except (PreparationError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    paths = AutomationPaths.build(
        project_root=args.project_root,
        output_root=args.output_root,
        process_slug=args.slug,
    )

    print(f"Process: {manifest.process_title}")
    print(f"Run ID: {manifest.run_id}")
    print(f"Mode: {manifest.generation_mode}")
    print(f"Input package: {paths.input_dir}")
    print(f"Manifest: {paths.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
