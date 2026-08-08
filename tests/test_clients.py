from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import requests
import responses

from portugal_external_growth.clients.bpstat import BPstatClient, flatten_jsonstat
from portugal_external_growth.clients.comtrade import (
    ComtradeAPIError,
    ComtradeClient,
    ComtradePartialResponseError,
    ComtradeProductRequest,
    ComtradeRequest,
    ComtradeSubscriptionKeyRequired,
)
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

    raw, frame, request_url, http_metadata = client.fetch(request)
    raw_path, csv_path = client.save(
        request,
        raw,
        frame,
        request_url,
        http_metadata,
        tmp_path,
        overwrite=True,
    )

    assert frame["year"].tolist() == [1961, 1962]
    assert raw_path.exists()
    assert csv_path.exists()
    metadata = json.loads(raw_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert metadata["rows"] == 2
    assert metadata["parameters"]["country_code"] == "PRT"
    assert metadata["http_status"] == 200
    assert metadata["content_type"] == "application/json"
    assert metadata["query_parameters"]["date"] == "1961:1962"


@responses.activate
def test_world_bank_client_rejects_unexpected_response_shape() -> None:
    responses.add(
        responses.GET,
        "https://api.worldbank.org/v2/country/PRT/indicator/NY.GDP.MKTP.KD.ZG",
        json={"unexpected": True},
    )
    request = WorldBankRequest("PRT", "NY.GDP.MKTP.KD.ZG", 1961, 1962)
    client = WorldBankClient(requests.Session())

    with pytest.raises(ValueError, match="Unexpected World Bank API response structure"):
        client.fetch(request)


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

    raw, frame, request_url, http_metadata = client.fetch(request)
    raw_path, csv_path = client.save(
        request,
        raw,
        frame,
        request_url,
        http_metadata,
        tmp_path,
        overwrite=True,
    )
    availability_path = client.save_availability_response(
        request,
        raw,
        frame,
        request_url,
        http_metadata,
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
    assert metadata["http_status"] == 200
    assert metadata["query_parameters"]["subscription-key"] == "***REDACTED***"
    assert metadata["territorial_definition"].startswith("UN Comtrade partner")
    assert availability_metadata["purpose"] == "historical_coverage_audit"


@responses.activate
def test_comtrade_client_rejects_non_mapping_payload() -> None:
    responses.add(
        responses.GET,
        "https://comtradeapi.un.org/public/v1/preview/C/A/S1",
        json=[],
    )
    client = ComtradeClient(requests.Session())
    request = ComtradeRequest(year=1962, reporter_code=620, partner_codes=(0,), flow_code="X")

    with pytest.raises(ValueError, match="Unexpected UN Comtrade response structure"):
        client.fetch(request)


@responses.activate
def test_comtrade_client_rejects_missing_data_list() -> None:
    responses.add(
        responses.GET,
        "https://comtradeapi.un.org/public/v1/preview/C/A/S1",
        json={"data": {}},
    )
    client = ComtradeClient(requests.Session())
    request = ComtradeRequest(year=1962, reporter_code=620, partner_codes=(0,), flow_code="X")

    with pytest.raises(ValueError, match="does not contain a data list"):
        client.fetch(request)


@responses.activate
def test_comtrade_client_rejects_api_error_payload() -> None:
    responses.add(
        responses.GET,
        "https://comtradeapi.un.org/public/v1/preview/C/A/S1",
        json={"data": [], "error": "invalid reporter"},
    )
    client = ComtradeClient(requests.Session())
    request = ComtradeRequest(year=1962, reporter_code=620, partner_codes=(0,), flow_code="X")

    with pytest.raises(ComtradeAPIError, match="invalid reporter"):
        client.fetch(request)


def test_comtrade_product_fetch_requires_subscription_key() -> None:
    client = ComtradeClient(requests.Session())
    request = ComtradeProductRequest(
        year=1962,
        reporter_code=620,
        partner_code=0,
        flow_code="X",
        commodity_codes=("0", "1"),
    )

    with pytest.raises(ComtradeSubscriptionKeyRequired):
        client.fetch_product(request)


@responses.activate
def test_comtrade_product_fetch_count_checks_and_saves(tmp_path: Path) -> None:
    url = "https://comtradeapi.un.org/data/v1/get/C/A/S1"
    responses.add(responses.GET, url, json={"count": 1, "data": []})
    responses.add(
        responses.GET,
        url,
        json={
            "count": 1,
            "data": [
                {
                    "refYear": 1962,
                    "flowCode": "X",
                    "classificationCode": "S1",
                    "cmdCode": "0",
                    "cmdDesc": "Food",
                    "reporterCode": 620,
                    "partnerCode": 0,
                    "primaryValue": 100.0,
                    "isReported": True,
                    "isOriginalClassification": True,
                    "legacyEstimationFlag": 0,
                    "isAggregate": False,
                }
            ],
        },
    )
    client = ComtradeClient(requests.Session(), subscription_key="secret-key")
    request = ComtradeProductRequest(
        year=1962,
        reporter_code=620,
        partner_code=0,
        flow_code="X",
        commodity_codes=("0",),
        max_records=250000,
    )

    raw, frame, request_url, metadata = client.fetch_product(request)
    raw_path, csv_path = client.save_product_response(
        request,
        raw,
        frame,
        request_url,
        metadata,
        tmp_path,
        overwrite=True,
    )

    assert frame.loc[0, "cmdCode"] == "0"
    assert raw_path.exists()
    assert csv_path.exists()
    sidecar = json.loads(raw_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert sidecar["endpoint_mode"] == "subscription_final_data"
    assert sidecar["query_parameters"]["subscription-key"] == "***REDACTED***"
    assert "secret-key" not in sidecar["request_url"]


@responses.activate
def test_comtrade_product_fetch_rejects_over_limit_count() -> None:
    responses.add(
        responses.GET,
        "https://comtradeapi.un.org/data/v1/get/C/A/S1",
        json={"count": 501, "data": []},
    )
    client = ComtradeClient(requests.Session(), subscription_key="secret-key")
    request = ComtradeProductRequest(
        year=1962,
        reporter_code=620,
        partner_code=0,
        flow_code="X",
        commodity_codes=("0",),
        max_records=500,
    )

    with pytest.raises(ComtradePartialResponseError, match="split the query further"):
        client.fetch_product(request)


@responses.activate
def test_comtrade_product_fetch_rejects_missing_count() -> None:
    responses.add(
        responses.GET,
        "https://comtradeapi.un.org/data/v1/get/C/A/S1",
        json={"data": []},
    )
    client = ComtradeClient(requests.Session(), subscription_key="secret-key")
    request = ComtradeProductRequest(
        year=1962,
        reporter_code=620,
        partner_code=0,
        flow_code="X",
        commodity_codes=("0",),
    )

    with pytest.raises(ValueError, match="missing integer count"):
        client.fetch_product_count(request)


@responses.activate
def test_comtrade_product_fetch_rejects_partial_data_response() -> None:
    url = "https://comtradeapi.un.org/data/v1/get/C/A/S1"
    responses.add(responses.GET, url, json={"count": 2, "data": []})
    responses.add(
        responses.GET,
        url,
        json={"count": 2, "data": [{"cmdCode": "0"}]},
    )
    client = ComtradeClient(requests.Session(), subscription_key="secret-key")
    request = ComtradeProductRequest(
        year=1962,
        reporter_code=620,
        partner_code=0,
        flow_code="X",
        commodity_codes=("0",),
        max_records=2,
    )

    with pytest.raises(ComtradePartialResponseError, match="response may be partial"):
        client.fetch_product(request)


@responses.activate
def test_comtrade_product_fetch_rejects_application_error() -> None:
    responses.add(
        responses.GET,
        "https://comtradeapi.un.org/data/v1/get/C/A/S1",
        json={"data": [], "error": "invalid commodity"},
    )
    client = ComtradeClient(requests.Session(), subscription_key="secret-key")
    request = ComtradeProductRequest(
        year=1962,
        reporter_code=620,
        partner_code=0,
        flow_code="X",
        commodity_codes=("bad",),
    )

    with pytest.raises(ComtradeAPIError, match="invalid commodity"):
        client.fetch_product_count(request)


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
    raw, frame, request_url, http_metadata = client.fetch_dataset(
        domain_id=1, dataset_id="DS", series_ids=(123,)
    )
    raw_path, csv_path = client.save(
        raw_json=raw,
        frame=frame,
        request_url=request_url,
        http_metadata=http_metadata,
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
    sidecar = json.loads(raw_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert sidecar["http_status"] == 200
    assert sidecar["api_version"] == "BPstat Data API v1"


@responses.activate
def test_bpstat_client_rejects_unexpected_series_metadata() -> None:
    responses.add(
        responses.GET,
        "https://bpstat.bportugal.pt/data/v1/series/",
        json=[{"id": 123}, "bad item"],
    )
    client = BPstatClient(requests.Session())

    with pytest.raises(ValueError, match="Unexpected BPstat series metadata response"):
        client.fetch_series_metadata((123,))


@responses.activate
def test_bpstat_client_rejects_unexpected_dataset_payload() -> None:
    responses.add(
        responses.GET,
        "https://bpstat.bportugal.pt/data/v1/domains/1/datasets/DS",
        json=[],
    )
    client = BPstatClient(requests.Session())

    with pytest.raises(ValueError, match="Unexpected BPstat dataset response"):
        client.fetch_dataset(domain_id=1, dataset_id="DS", series_ids=(123,))


def test_flatten_jsonstat_supports_sparse_values() -> None:
    payload = _jsonstat_payload()
    payload["value"] = {"1": 2.0}

    frame = flatten_jsonstat(payload)

    assert pd.isna(frame.loc[0, "value"])
    assert frame.loc[1, "value"] == 2.0


def test_flatten_jsonstat_supports_list_indexes_and_label_fallbacks() -> None:
    payload = _jsonstat_payload()
    payload["dimension"]["year"]["category"] = {"index": ["1961", "1962"]}
    payload["value"] = None

    frame = flatten_jsonstat(payload)

    assert frame["year"].tolist() == ["1961", "1962"]
    assert frame["year_label"].tolist() == ["1961", "1962"]
    assert frame["value"].isna().all()


def test_flatten_jsonstat_rejects_bad_dimension_metadata() -> None:
    payload = _jsonstat_payload()
    payload["dimension"].pop("year")

    with pytest.raises(ValueError, match="Missing metadata"):
        flatten_jsonstat(payload)


@pytest.mark.parametrize(
    ("payload_update", "message"),
    [
        ({"id": "series", "size": [1]}, "missing id or size"),
        ({"dimension": []}, "missing dimension metadata"),
        ({"id": ["series"], "size": [1, 2]}, "id and size arrays differ"),
    ],
)
def test_flatten_jsonstat_rejects_invalid_top_level_metadata(
    payload_update: dict[str, object],
    message: str,
) -> None:
    payload = _jsonstat_payload()
    payload.update(payload_update)

    with pytest.raises(ValueError, match=message):
        flatten_jsonstat(payload)


def test_flatten_jsonstat_rejects_missing_category_metadata() -> None:
    payload = _jsonstat_payload()
    payload["dimension"]["series"] = {}

    with pytest.raises(ValueError, match="Missing category metadata"):
        flatten_jsonstat(payload)


def test_flatten_jsonstat_rejects_unsupported_category_index() -> None:
    payload = _jsonstat_payload()
    payload["dimension"]["series"]["category"]["index"] = "S1"

    with pytest.raises(ValueError, match="Unsupported category index"):
        flatten_jsonstat(payload)


def test_flatten_jsonstat_rejects_unexpected_category_count() -> None:
    payload = _jsonstat_payload()
    payload["dimension"]["series"]["category"]["index"] = {"S1": 0, "S2": 1}

    with pytest.raises(ValueError, match="Unexpected category count"):
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
