from __future__ import annotations

from pathlib import Path

import pytest
import requests
import responses

from portugal_external_growth.config import load_yaml
from portugal_external_growth.http import build_session, get_bytes
from portugal_external_growth.settings import Settings


def test_load_yaml_accepts_mapping(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text("answer: 42\n", encoding="utf-8")

    assert load_yaml(path) == {"answer": 42}


def test_load_yaml_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "config.yml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(TypeError, match="Expected a mapping"):
        load_yaml(path)


def test_settings_resolves_root_and_rejects_reversed_years(tmp_path: Path) -> None:
    settings = Settings(root=tmp_path, start_year=1973, end_year=1960)

    assert settings.resolved_root() == tmp_path.resolve()
    with pytest.raises(ValueError, match="start_year"):
        settings.validate_year_range()


def test_settings_reads_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEG_START_YEAR", "1962")
    monkeypatch.setenv("PEG_END_YEAR", "1973")
    monkeypatch.setenv("PEG_HTTP_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("PEG_COMTRADE_SUBSCRIPTION_KEY", "secret")

    settings = Settings()

    assert settings.start_year == 1962
    assert settings.end_year == 1973
    assert settings.http_timeout_seconds == 15
    assert settings.comtrade_subscription_key == "secret"


def test_build_session_sets_project_user_agent() -> None:
    session = build_session()

    assert session.headers["User-Agent"] == "portugal-external-growth/0.1.0"


@responses.activate
def test_get_bytes_returns_normalised_response() -> None:
    responses.add(
        responses.GET,
        "https://example.test/data",
        json={"ok": True},
        headers={"X-Test": "yes"},
    )

    response = get_bytes(
        requests.Session(),
        "https://example.test/data",
        params={"q": "1"},
        timeout_seconds=5,
    )

    assert response.status_code == 200
    assert response.headers["X-Test"] == "yes"
    assert response.json() == {"ok": True}
    assert response.url.endswith("?q=1")


@responses.activate
def test_get_bytes_raises_for_http_errors() -> None:
    responses.add(responses.GET, "https://example.test/fail", status=500)

    with pytest.raises(requests.HTTPError):
        get_bytes(
            requests.Session(),
            "https://example.test/fail",
            params=None,
            timeout_seconds=5,
        )
