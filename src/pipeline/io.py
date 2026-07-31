"""Small JSON and file helpers used by automation modules."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"JSON file not found: {source}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {source}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {source}.")

    return payload


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def copy_file(source: str | Path, target: str | Path) -> Path:
    source_path = Path(source)
    target_path = Path(target)
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    return target_path
