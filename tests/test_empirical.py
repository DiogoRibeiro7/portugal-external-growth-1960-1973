from __future__ import annotations

from portugal_external_growth.empirical import (
    build_empirical_prerequisite_status,
    empty_coefficients,
)


def test_empirical_prerequisites_are_blocked_by_default() -> None:
    status = build_empirical_prerequisite_status()
    assert set(status["status"]) == {"not_satisfied"}


def test_empirical_coefficients_are_empty() -> None:
    coefficients = empty_coefficients()
    assert coefficients.empty
    assert "estimate" in coefficients.columns
