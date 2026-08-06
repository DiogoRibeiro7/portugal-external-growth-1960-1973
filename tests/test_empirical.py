from __future__ import annotations

from portugal_external_growth.empirical import (
    build_empirical_prerequisite_status,
    build_empirical_risk_notes,
    build_model_specification_registry,
    empty_coefficients,
    empty_design_matrix,
    empty_diagnostics,
)


def test_empirical_prerequisites_are_blocked_by_default() -> None:
    status = build_empirical_prerequisite_status()
    assert set(status["status"]) == {"not_satisfied"}


def test_empirical_coefficients_are_empty() -> None:
    coefficients = empty_coefficients()
    assert coefficients.empty
    assert "estimate" in coefficients.columns


def test_empirical_placeholder_outputs_are_schema_stable() -> None:
    design = empty_design_matrix()
    diagnostics = empty_diagnostics()
    specs = build_model_specification_registry()
    notes = build_empirical_risk_notes()

    assert design.empty
    assert "colonial_exposure" in design.columns
    assert diagnostics.loc[0, "status"] == "failed"
    assert set(specs["status"]) == {"blocked_pending_prerequisites"}
    assert "No model has been fit" in notes
