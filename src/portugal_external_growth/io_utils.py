"""Safe local I/O, provenance records, and checksums."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

LF_NORMALISED_TEXT_SUFFIXES = {
    ".cff",
    ".csv",
    ".json",
    ".lock",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
LF_NORMALISED_TEXT_NAMES = {
    ".gitattributes",
    ".gitignore",
    "Makefile",
}


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


def repository_file_fingerprint(path: Path, *, relative_path: str) -> tuple[int, str]:
    """Return size and SHA-256 after applying repository text EOL normalisation."""

    payload = path.read_bytes()
    if _lf_normalised_repository_path(relative_path):
        payload = payload.replace(b"\r\n", b"\n")
    return len(payload), hashlib.sha256(payload).hexdigest()


def _lf_normalised_repository_path(relative_path: str) -> bool:
    path = Path(relative_path)
    return path.suffix in LF_NORMALISED_TEXT_SUFFIXES or path.name in LF_NORMALISED_TEXT_NAMES


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


def write_text_lf(path: Path, text: str, *, overwrite: bool = True) -> None:
    """Write UTF-8 text using deterministic LF line endings."""

    payload = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    atomic_write_bytes(path, payload, overwrite=overwrite)


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
    existing_metadata = _read_existing_metadata(sidecar)
    normalised_metadata = _normalise_metadata(metadata, root=Path.cwd())
    output_sha256 = sha256_file(csv_path)
    creation_timestamp = _creation_timestamp(
        normalised_metadata,
        root=Path.cwd(),
        existing_metadata=existing_metadata,
        output_sha256=output_sha256,
    )
    complete_metadata: dict[str, Any] = {
        **normalised_metadata,
        "file": _metadata_path(csv_path),
        "sha256": output_sha256,
        "creation_timestamp_utc": creation_timestamp,
        "rows": len(frame),
        "columns": [str(column) for column in frame.columns],
        "schema": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        "date_range": _date_range(frame),
        "validation_findings": normalised_metadata.get("validation_findings", []),
        "source_licence": normalised_metadata.get("source_licence", "not_specified"),
        "access_conditions": normalised_metadata.get("access_conditions", "not_specified"),
    }
    atomic_write_json(sidecar, complete_metadata, overwrite=overwrite)
    return sidecar


def _metadata_path(path: Path) -> str:
    return repo_relative_path(path, root=Path.cwd())


def _read_existing_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _creation_timestamp(
    metadata: Mapping[str, Any],
    *,
    root: Path,
    existing_metadata: Mapping[str, Any],
    output_sha256: str,
) -> str:
    explicit = metadata.get("creation_timestamp_utc")
    if explicit:
        return str(explicit)
    environment_timestamp = os.getenv("PEG_METADATA_TIMESTAMP_UTC")
    if environment_timestamp:
        return environment_timestamp
    if existing_metadata.get("sha256") == output_sha256 and existing_metadata.get(
        "creation_timestamp_utc"
    ):
        return str(existing_metadata["creation_timestamp_utc"])
    try:
        return subprocess.run(
            ["git", "show", "-s", "--format=%cI", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def repo_relative_path(path: str | Path, *, root: Path) -> str:
    """Return a stable POSIX path relative to the repository when possible."""

    candidate = Path(path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return candidate.as_posix()


def _normalise_metadata(metadata: Mapping[str, Any], *, root: Path) -> dict[str, Any]:
    output = dict(metadata)
    source_files = output.get("source_files")
    if isinstance(source_files, list):
        normalised_sources = [
            repo_relative_path(path, root=root) for path in source_files if isinstance(path, str)
        ]
        output["source_files"] = normalised_sources
        output.setdefault("input_artifacts", _input_artifacts(normalised_sources, root=root))
    return output


def _input_artifacts(source_files: list[str], *, root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for source_file in source_files:
        path = root / source_file
        if not path.is_file():
            continue
        artifacts.append(
            {
                "path": source_file,
                "sha256": sha256_file(path),
            }
        )
    return artifacts


def _date_range(frame: pd.DataFrame) -> dict[str, int] | None:
    for column in ("year", "expected_year", "publication_year"):
        if column not in frame.columns:
            continue
        years = pd.to_numeric(frame[column], errors="coerce").dropna()
        if years.empty:
            continue
        return {"start_year": int(years.min()), "end_year": int(years.max())}
    return None


def sanitise_url(url: str, secrets: tuple[str, ...]) -> str:
    """Remove known secret values from a URL before writing provenance."""

    sanitised = url
    for secret in secrets:
        if secret:
            sanitised = sanitised.replace(secret, "***REDACTED***")
    return sanitised
