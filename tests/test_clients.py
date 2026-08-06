from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import requests
import responses

from portugal_external_growth.clients.bpstat import BPstatClient, flatten_jsonstat
from portugal_external_growth.clients.comtrade import ComtradeClient, ComtradeRequest
from portugal_external_growth.clients.world_bank import WorldBankClient, WorldBankRequest


@responses.activate
def test_world_bank_client_fetches_and_saves_snapshot(tmp_path: Path) -> None:
    url = "https://api.worldbank.org/v2/country/PRT/indicator/NY.GDP.MKTP.KD.ZG"
    responses.add(
        responses.GET,
        url,
        json=[
            {"page": 1},
            [
                {"date": "1962", "value": 6.5, "unit": "", "obs_status": ""},
                {"date": "not-a-year", "value": 0.0},
                {"date": "1961", "value": 5.1, "unit": "", "obs_status": "A"},
            ],
        ],
    )
    request = WorldBankRequest("PRT", "NY.GDP.MKTP.KD.ZG", 1961, 1962)
    client = WorldBankClient(requests.Session())

    raw, frame, request_url = client.fetch(request)
    raw_path, csv_path = client.save(request, raw, frame, request_url, tmp_path, overwrite=True)

    assert frame["year"].tolist() == [1961, 1962]
    assert raw_path.exists()
    assert csv_path.exists()
    metadata = json.loads(raw_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert metadata["rows"] == 2
    assert metadata["parameters"]["country_code"] == "PRT"


@responses.activate
def test_comtrade_client_fetches_preview_and_redacts_subscription_key(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        "https://comtradeapi.un.org/data/v1/get/C/A/S1",
        json={
            "data": [
                {
                    "period": 1962,
                    "reporterCode": 620,
                    "partnerCode": 24,
                    "partnerDesc": "Angola",
                    "flowCode": "X",
                    "cmdCode": "TOTAL",
                    "primaryValue": 10.0,
                }
            ]
        },
    )
    request = ComtradeRequest(
        year=1962,
        reporter_code=620,
        partner_codes=(0, 24),
        flow_code="X",
        classification_code="S1",
    )
    client = ComtradeClient(requests.Session(), subscription_key="secret-key")

    raw, frame, request_url = client.fetch(request)
    raw_path, csv_path = client.save(request, raw, frame, request_url, tmp_path, overwrite=True)
    availability_path = client.save_availability_response(
        request,
        raw,
        frame,
        request_url,
        tmp_path,
        overwrite=True,
    )

    metadata = json.loads(raw_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    availability_metadata = json.loads(
        availability_path.with_suffix(".metadata.json").read_text(encoding="utf-8")
    )
    assert frame.loc[0, "partnerDesc"] == "Angola"
    assert csv_path.exists()
    assert "secret-key" not in metadata["request_url"]
    assert metadata["endpoint_mode"] == "free_key"
    assert availability_metadata["purpose"] == "historical_coverage_audit"


@responses.activate
def test_bpstat_client_fetches_metadata_dataset_and_saves(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        "https://bpstat.bportugal.pt/data/v1/series/",
        json=[{"id": 123, "domain_ids": [1], "dataset_id": "DS"}],
    )
    responses.add(
        responses.GET,
        "https://bpstat.bportugal.pt/data/v1/domains/1/datasets/DS",
        json=_jsonstat_payload(),
    )
    client = BPstatClient(requests.Session())

    metadata = client.fetch_series_metadata((123,))
    raw, frame, request_url = client.fetch_dataset(domain_id=1, dataset_id="DS", series_ids=(123,))
    raw_path, csv_path = client.save(
        raw_json=raw,
        frame=frame,
        request_url=request_url,
        series_ids=(123,),
        root=tmp_path,
        overwrite=True,
    )

    assert metadata[0]["dataset_id"] == "DS"
    assert frame[["series", "year", "value"]].to_dict(orient="records") == [
        {"series": "S1", "year": "1961", "value": 1.0},
        {"series": "S1", "year": "1962", "value": 2.0},
    ]
    assert raw_path.exists()
    assert csv_path.exists()


def test_flatten_jsonstat_supports_sparse_values() -> None:
    payload = _jsonstat_payload()
    payload["value"] = {"1": 2.0}

    frame = flatten_jsonstat(payload)

    assert pd.isna(frame.loc[0, "value"])
    assert frame.loc[1, "value"] == 2.0


def test_flatten_jsonstat_rejects_bad_dimension_metadata() -> None:
    payload = _jsonstat_payload()
    payload["dimension"].pop("year")

    with pytest.raises(ValueError, match="Missing metadata"):
        flatten_jsonstat(payload)


def _jsonstat_payload() -> dict[str, Any]:
    return {
        "id": ["series", "year"],
        "size": [1, 2],
        "dimension": {
            "series": {
                "category": {
                    "index": {"S1": 0},
                    "label": {"S1": "Exports"},
                }
            },
            "year": {
                "category": {
                    "index": {"1961": 0, "1962": 1},
                    "label": {"1961": "1961", "1962": "1962"},
                }
            },
        },
        "value": [1.0, 2.0],
    }
