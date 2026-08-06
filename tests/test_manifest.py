from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.validation import build_file_manifest


def test_committed_manifest_matches_repository_files() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "results/manifests/current_manifest.csv"

    committed = pd.read_csv(manifest_path).sort_values("relative_path").reset_index(drop=True)
    actual = build_file_manifest(root).sort_values("relative_path").reset_index(drop=True)

    pd.testing.assert_frame_equal(
        committed[["relative_path", "size_bytes", "sha256", "artifact_role"]],
        actual[["relative_path", "size_bytes", "sha256", "artifact_role"]],
        check_dtype=False,
    )
