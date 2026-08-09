from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from pytest import MonkeyPatch

from portugal_external_growth.io_utils import write_dataframe_with_metadata, write_text_lf


def test_metadata_records_relative_input_hashes_and_schema(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "data/raw/source.csv"
    source.parent.mkdir(parents=True)
    source.write_text("year,value\n1962,1\n", encoding="utf-8")

    write_dataframe_with_metadata(
        pd.DataFrame({"year": [1962], "value": [1.0]}),
        tmp_path / "results/live/table.csv",
        metadata={"source_files": [str(source)]},
    )

    metadata = json.loads((tmp_path / "results/live/table.csv.metadata.json").read_text())

    assert metadata["source_files"] == ["data/raw/source.csv"]
    assert metadata["input_artifacts"][0]["path"] == "data/raw/source.csv"
    assert metadata["input_artifacts"][0]["sha256"]
    assert metadata["schema"] == {"year": "int64", "value": "float64"}
    assert metadata["date_range"] == {"start_year": 1962, "end_year": 1962}
    assert "creation_timestamp_utc" in metadata


def test_metadata_uses_explicit_reproducible_creation_timestamp(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PEG_METADATA_TIMESTAMP_UTC", "2026-08-09T00:00:00Z")

    write_dataframe_with_metadata(
        pd.DataFrame({"value": [1]}),
        tmp_path / "results/live/table.csv",
        metadata={"stage": "test"},
    )

    metadata = json.loads((tmp_path / "results/live/table.csv.metadata.json").read_text())

    assert metadata["creation_timestamp_utc"] == "2026-08-09T00:00:00Z"


def test_write_text_lf_normalises_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "report.txt"

    write_text_lf(path, "a\r\nb\rc\n")

    assert path.read_bytes() == b"a\nb\nc\n"
