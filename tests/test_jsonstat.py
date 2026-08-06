from __future__ import annotations

from portugal_external_growth.clients.bpstat import flatten_jsonstat


def test_flatten_jsonstat_dense_values() -> None:
    payload = {
        "id": ["series", "time"],
        "size": [1, 2],
        "dimension": {
            "series": {"category": {"index": {"1": 0}, "label": {"1": "GDP"}}},
            "time": {
                "category": {
                    "index": {"1960": 0, "1961": 1},
                    "label": {"1960": "1960", "1961": "1961"},
                }
            },
        },
        "value": [100.0, 105.0],
    }
    result = flatten_jsonstat(payload)
    assert result["value"].tolist() == [100.0, 105.0]
    assert result["time"].tolist() == ["1960", "1961"]
