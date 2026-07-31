from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.finalize import FinalizationError, validate_worker_identity
from pipeline.kaggle_client import (
    KaggleGenerationService,
    KaggleSettings,
)
from pipeline.models import RunManifest, WorkerRunResult
from pipeline.paths import AutomationPaths


def manifest() -> RunManifest:
    return RunManifest(
        run_id="suivi-20260731-test",
        created_at_utc=datetime.now(timezone.utc),
        process_slug="suivi_commandes",
        process_id="Id_test",
        process_title="Suivi des commandes",
        bpmn_filename="Suivi des commandes.bpmn",
        bpmn_path="bpmn_files/Suivi des commandes.bpmn",
        generation_mode="both",
        model_name="Qwen/Qwen3-8B",
        git_commit="abc123",
        expected_outputs=[
            "generated_procedure.json",
            "procedure_validation_report.json",
            "generated_narrative.json",
            "narrative_validation_report.json",
            "run_result.json",
        ],
    )


def worker_result(**updates) -> WorkerRunResult:
    payload = {
        "run_id": "suivi-20260731-test",
        "generation_mode": "both",
        "process_slug": "suivi_commandes",
        "process_id": "Id_test",
        "process_title": "Suivi des commandes",
        "model_name": "Qwen/Qwen3-8B",
        "git_commit": "abc123",
        "procedure": {
            "status": "success",
            "generated_file": "generated_procedure.json",
            "validation_file": "procedure_validation_report.json",
        },
        "narrative": {
            "status": "success",
            "generated_file": "generated_narrative.json",
            "validation_file": "narrative_validation_report.json",
        },
    }
    payload.update(updates)
    return WorkerRunResult.model_validate(payload)


def test_paths_build_expected_layout(tmp_path: Path) -> None:
    paths = AutomationPaths.build(
        project_root=tmp_path,
        output_root="output",
        process_slug="suivi_commandes",
    )
    assert paths.input_dir == (
        tmp_path / "output/suivi_commandes/run/input"
    )
    assert paths.download_dir.name == "download"


def test_manifest_requires_mode_outputs() -> None:
    payload = manifest().model_dump()
    payload["expected_outputs"] = ["run_result.json"]
    with pytest.raises(ValueError):
        RunManifest.model_validate(payload)


def test_worker_identity_rejects_stale_run() -> None:
    stale = worker_result(run_id="old-run")
    with pytest.raises(FinalizationError, match="does not belong"):
        validate_worker_identity(manifest(), stale)


def test_status_parser() -> None:
    assert KaggleGenerationService.parse_kernel_status(
        'kernel has status "complete"'
    ) == "complete"
    assert KaggleGenerationService.parse_kernel_status(
        'kernel has status "running"'
    ) == "running"
    assert KaggleGenerationService.parse_kernel_status(
        'kernel has status "error"'
    ) == "error"


def test_staging_writes_kaggle_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    notebook = project / "notebooks/worker.ipynb"
    notebook.parent.mkdir()
    notebook.write_text('{"cells": []}', encoding="utf-8")

    paths = AutomationPaths.build(
        project_root=project,
        output_root="output",
        process_slug="suivi_commandes",
    )
    paths.ensure_base_directories()
    paths.input_dir.mkdir(parents=True)

    run_manifest = manifest()
    paths.manifest_path.write_text(
        json.dumps(run_manifest.model_dump(mode="json")),
        encoding="utf-8",
    )
    (paths.input_dir / "run_manifest.json").write_text(
        paths.manifest_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (paths.input_dir / "operation_contexts.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (paths.input_dir / "narrative_plan.json").write_text(
        "{}",
        encoding="utf-8",
    )

    service = KaggleGenerationService(
        paths=paths,
        settings=KaggleSettings(username="example-user"),
        notebook_path=notebook,
        client=object(),  # stage() does not call the CLI client.
    )
    service.stage()

    dataset_metadata = json.loads(
        (paths.dataset_stage_dir / "dataset-metadata.json")
        .read_text(encoding="utf-8")
    )
    kernel_metadata = json.loads(
        (paths.kernel_stage_dir / "kernel-metadata.json")
        .read_text(encoding="utf-8")
    )

    assert dataset_metadata["id"] == (
        "example-user/bpmn-generation-inputs"
    )
    assert kernel_metadata["enable_gpu"] is True
    assert kernel_metadata["dataset_sources"] == [
        "example-user/bpmn-generation-inputs"
    ]
