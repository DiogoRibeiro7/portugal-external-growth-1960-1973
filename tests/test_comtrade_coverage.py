from __future__ import annotations

import pandas as pd

from portugal_external_growth.transforms import compile_comtrade_coverage_audit


def test_comtrade_coverage_flags_missing_years() -> None:
    matrix = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S1",
                "reporter_code": 620,
                "partner_code": 0,
                "partner_desc": "World",
                "trade_value_usd": 100.0,
                "is_world_record": True,
                "raw_records": 1,
            }
        ]
    )
    _, audit, _ = compile_comtrade_coverage_audit(
        [matrix],
        colonial_partner_codes=(24,),
        expected_years=(1962, 1963),
        expected_flow_codes=("X",),
    )
    assert not bool(audit.loc[audit["year"] == 1963, "reporter_available"].iloc[0])


def test_comtrade_coverage_marks_duplicate_keys() -> None:
    matrix = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S1",
                "reporter_code": 620,
                "partner_code": 24,
                "partner_desc": "Angola",
                "trade_value_usd": 10.0,
                "is_world_record": False,
                "raw_records": 2,
            },
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S1",
                "reporter_code": 620,
                "partner_code": 24,
                "partner_desc": "Angola",
                "trade_value_usd": 10.0,
                "is_world_record": False,
                "raw_records": 2,
            },
        ]
    )
    coverage, _, _ = compile_comtrade_coverage_audit(
        [matrix],
        colonial_partner_codes=(24,),
        expected_years=(1962,),
        expected_flow_codes=("X",),
    )
    assert coverage["duplicate_key"].all()


def test_comtrade_coverage_detects_classification_changes() -> None:
    matrix = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S1",
                "reporter_code": 620,
                "partner_code": 0,
                "partner_desc": "World",
                "trade_value_usd": 100.0,
                "is_world_record": True,
                "raw_records": 1,
            },
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S2",
                "reporter_code": 620,
                "partner_code": 0,
                "partner_desc": "World",
                "trade_value_usd": 100.0,
                "is_world_record": True,
                "raw_records": 1,
            },
        ]
    )
    _, audit, _ = compile_comtrade_coverage_audit(
        [matrix],
        colonial_partner_codes=(24,),
        expected_years=(1962,),
        expected_flow_codes=("X",),
    )
    assert bool(audit.loc[0, "multiple_classifications_available"])


def test_comtrade_coverage_uses_configured_classification_preference() -> None:
    matrix = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S1",
                "reporter_code": 620,
                "partner_code": 0,
                "partner_desc": "World",
                "trade_value_usd": 100.0,
                "is_world_record": True,
                "raw_records": 1,
            },
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S2",
                "reporter_code": 620,
                "partner_code": 0,
                "partner_desc": "World",
                "trade_value_usd": 200.0,
                "is_world_record": True,
                "raw_records": 1,
            },
        ]
    )

    _, audit, _ = compile_comtrade_coverage_audit(
        [matrix],
        colonial_partner_codes=(24,),
        expected_years=(1962,),
        expected_flow_codes=("X",),
        preferred_classification_codes=("S2", "S1"),
    )

    assert audit.loc[0, "preferred_classification_for_checks"] == "S2"
    assert audit.loc[0, "world_value_usd"] == 200.0
