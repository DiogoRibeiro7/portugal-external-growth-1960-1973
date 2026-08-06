"""YAML configuration loaders with explicit type checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping and reject invalid top-level structures."""

    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected a mapping in {path}, got {type(payload).__name__}")
    return payload
