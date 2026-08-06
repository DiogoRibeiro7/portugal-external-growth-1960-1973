"""Safe local I/O, provenance records, and checksums."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(tz=UTC).isoformat()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, payload: bytes, *, overwrite: bool = False) -> None:
    """Write bytes atomically and prevent accidental raw-data replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")

    file_descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary_name).replace(path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: Mapping[str, Any], *, overwrite: bool = False) -> None:
    """Write a JSON object atomically."""

    encoded = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()
    atomic_write_bytes(path, encoded, overwrite=overwrite)


def write_dataframe_with_metadata(
    frame: pd.DataFrame,
    csv_path: Path,
    *,
    metadata: Mapping[str, Any],
    overwrite: bool = True,
) -> Path:
    """Write a deterministic CSV and a sidecar metadata record."""

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    atomic_write_bytes(csv_path, csv_payload, overwrite=overwrite)

    sidecar = csv_path.with_suffix(csv_path.suffix + ".metadata.json")
    complete_metadata: dict[str, Any] = {
        **metadata,
        "created_at_utc": utc_now_iso(),
        "file": str(csv_path),
        "sha256": sha256_file(csv_path),
        "rows": len(frame),
        "columns": [str(column) for column in frame.columns],
    }
    atomic_write_json(sidecar, complete_metadata, overwrite=overwrite)
    return sidecar


def sanitise_url(url: str, secrets: tuple[str, ...]) -> str:
    """Remove known secret values from a URL before writing provenance."""

    sanitised = url
    for secret in secrets:
        if secret:
            sanitised = sanitised.replace(secret, "***REDACTED***")
    return sanitised
