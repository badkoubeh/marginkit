"""``decisions/0023``: ``schema_version`` becomes ``"3"`` (``Fit.diagnostics`` is a real,
appended field), and the v1/v2 schemas stay packaged, unchanged, for the reader path.

**Amendment 1** moves monotonicity off ``Diagnostics`` and onto a second appended field,
``Fit.monotonicity`` (a ``MonotonicityCheck``, last in field order, after ``diagnostics``),
populated on *every* ``fit_dose_response`` return path -- so ``Fit`` now carries two
diagnostic-like fields with different nullability: ``diagnostics`` only when the fit is ``OK``,
``monotonicity`` on every fresh result regardless of ``Status`` (``None`` only for a card read
from schema ``"1"``/``"2"``, which predate the field entirely).

Mirrors ``tests/unit/test_ratio_interval_schema_v2.py``'s own conventions for the previous bump
(``jsonschema.Draft202012Validator`` against ``load_schema()``'s ``$defs``, a recursive
``schema_version`` downgrade helper) rather than introducing new ones.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import jsonschema
import pytest

from marginkit import Scorecard, grid_break_point
from marginkit.report import SCHEMA_VERSION, from_dict, load_schema, to_dict
from marginkit.testing import fake_fit, fake_ratio, fake_threshold


def _downgrade_schema_version(obj: Any, version: str) -> Any:
    if isinstance(obj, dict):
        return {
            key: (version if key == "schema_version" else _downgrade_schema_version(value, version))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_downgrade_schema_version(item, version) for item in obj]
    return obj


class TestSchemaVersionIsNowThree:
    def test_schema_version_constant_is_3(self) -> None:
        assert SCHEMA_VERSION == "3"

    def test_a_freshly_built_fit_defaults_to_schema_version_3(self) -> None:
        assert fake_fit().schema_version == "3"

    def test_a_freshly_built_threshold_defaults_to_schema_version_3(self) -> None:
        assert fake_threshold().schema_version == "3"

    def test_a_freshly_built_ratio_defaults_to_schema_version_3(self) -> None:
        assert fake_ratio().schema_version == "3"

    def test_a_freshly_built_grid_break_point_defaults_to_schema_version_3(self) -> None:
        result = grid_break_point([0.0, 5.0, 10.0], [1.0, 0.95, 0.4], criterion=0.95)

        assert result.schema_version == "3"

    def test_a_freshly_built_scorecard_defaults_to_schema_version_3(self) -> None:
        card = Scorecard(results=(fake_fit(),), provenance={})

        assert card.schema_version == "3"


class TestOlderSchemasStayPackagedForTheReaderPath:
    def test_load_schema_1_still_works(self) -> None:
        schema = load_schema("1")

        assert isinstance(schema, dict)
        assert schema["properties"]["type"]["const"] == "Scorecard"

    def test_load_schema_2_still_works(self) -> None:
        schema = load_schema("2")

        assert isinstance(schema, dict)
        assert schema["properties"]["type"]["const"] == "Scorecard"

    def test_neither_v1_nor_v2_fit_schema_knows_about_diagnostics_or_monotonicity(self) -> None:
        """A card tagged ``schema_version: "1"`` or ``"2"`` could never have carried a
        ``diagnostics`` or ``monotonicity`` key -- the packaged v1/v2 documents must stay
        exactly as they were."""
        for version in ("1", "2"):
            schema = load_schema(version)
            assert "diagnostics" not in schema["$defs"]["Fit"]["properties"]
            assert "monotonicity" not in schema["$defs"]["Fit"]["properties"]

    def test_default_load_schema_is_v3(self) -> None:
        schema = load_schema()

        assert schema["$id"].endswith("v3")


class TestDiagnosticsIsInTheV3SchemaOnly:
    def test_fit_schema_v3_has_a_diagnostics_property(self) -> None:
        schema = load_schema()

        assert "diagnostics" in schema["$defs"]["Fit"]["properties"]

    def test_diagnostics_is_not_required_on_fit(self) -> None:
        """An appended field defaulting to ``None`` (decisions/0023, Appendix B item 4) is never
        mandatory."""
        schema = load_schema()

        assert "diagnostics" not in schema["$defs"]["Fit"]["required"]

    def test_schema_v3_defines_diagnostics(self) -> None:
        schema = load_schema()

        assert "Diagnostics" in schema["$defs"]

    def test_diagnostics_has_no_monotonicity_entry(self) -> None:
        """Amendment 1, item 2: the monotonicity entries moved out of ``Diagnostics``
        entirely."""
        schema = load_schema()

        assert "monotonicity" not in schema["$defs"]["Diagnostics"]["properties"]

    def test_a_fit_with_diagnostics_validates_against_the_v3_schema(self) -> None:
        diagnostics_payload = {
            "deviance": 1.0,
            "pearson_chi2": 1.0,
            "df": 1,
            "dispersion": 1.0,
            "link_aic": {"probit": 1.0, "logit": None, "cloglog": None},
            "link_status": {"probit": "OK", "logit": "NOT_CONVERGED", "cloglog": "SEPARATION"},
            "warnings": [],
        }
        schema = load_schema()
        validator = jsonschema.Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": "#/$defs/Fit"}
        )
        payload = to_dict(fake_fit())
        payload["diagnostics"] = diagnostics_payload

        errors = list(validator.iter_errors(payload))

        assert errors == []


class TestMonotonicityIsInTheV3SchemaOnly:
    """Amendment 1, item 8: ``Fit`` gains ``monotonicity`` (an object or ``null``), and
    ``MonotonicityCheck``/``AdjacentPair`` are added ``$defs`` with
    ``additionalProperties: false``, like every other object."""

    def test_fit_schema_v3_has_a_monotonicity_property(self) -> None:
        schema = load_schema()

        assert "monotonicity" in schema["$defs"]["Fit"]["properties"]

    def test_monotonicity_is_not_required_on_fit(self) -> None:
        schema = load_schema()

        assert "monotonicity" not in schema["$defs"]["Fit"]["required"]

    def test_schema_v3_defines_monotonicity_check_and_adjacent_pair(self) -> None:
        schema = load_schema()

        assert "MonotonicityCheck" in schema["$defs"]
        assert "AdjacentPair" in schema["$defs"]

    def test_monotonicity_check_and_adjacent_pair_reject_an_extra_key(self) -> None:
        schema = load_schema()
        for type_name in ("MonotonicityCheck", "AdjacentPair"):
            node = schema["$defs"][type_name]
            assert node.get("additionalProperties") is False, type_name

    def test_a_fit_with_monotonicity_validates_against_the_v3_schema(self) -> None:
        monotonicity_payload = {
            "direction": "decreasing",
            "alpha": 0.05,
            "dependence": "independent",
            "method": "fisher_exact_one_sided_holm",
            "pairs": [
                {
                    "severity_low": 0.0,
                    "severity_high": 0.01,
                    "successes_low": 57,
                    "trials_low": 200,
                    "successes_high": 143,
                    "trials_high": 300,
                    "p_value": 1.17e-05,
                    "holm_adjusted_p": 3.5e-05,
                    "flagged": True,
                }
            ],
            "any_flagged": True,
            "warnings": [],
        }
        schema = load_schema()
        validator = jsonschema.Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": "#/$defs/Fit"}
        )
        payload = to_dict(fake_fit())
        payload["monotonicity"] = monotonicity_payload

        errors = list(validator.iter_errors(payload))

        assert errors == []


class TestOlderCardsStillLoadUnderTheV3Reader:
    """A card genuinely written under ``schema_version == "1"`` or ``"2"`` -- simulated by
    downgrading a fresh card's own ``schema_version`` fields, per this file's module docstring --
    must still load through ``from_dict`` (Appendix B), preserving the downgraded version rather
    than being silently upgraded."""

    @pytest.mark.parametrize("version", ["1", "2"])
    def test_a_downgraded_grid_result_card_loads_and_keeps_its_version(self, version: str) -> None:
        grid = grid_break_point([0.0, 5.0, 10.0], [1.0, 0.95, 0.4], criterion=0.95)
        assert grid.schema_version == "3"  # freshly built: confirms the downgrade below is real
        card = Scorecard(results=(grid,), provenance={})

        payload = to_dict(card)
        downgraded_payload = _downgrade_schema_version(payload, version)
        reloaded = from_dict(json.loads(json.dumps(downgraded_payload)))

        assert isinstance(reloaded, Scorecard)
        assert reloaded.schema_version == version
        assert reloaded.results[0].schema_version == version

        expected_grid = dataclasses.replace(grid, schema_version=version)
        expected_card = dataclasses.replace(card, schema_version=version, results=(expected_grid,))
        assert reloaded == expected_card

    def test_v_999_payload_still_raises(self) -> None:
        grid = grid_break_point([0.0, 5.0, 10.0], [1.0, 0.95, 0.4], criterion=0.95)
        card = Scorecard(results=(grid,), provenance={})
        payload = to_dict(card)
        bad_payload = _downgrade_schema_version(payload, "999")

        with pytest.raises(ValueError):
            from_dict(json.loads(json.dumps(bad_payload)))
