"""Unit tests for ``marginkit.report``: ``to_dict`` / ``from_dict`` / ``load_schema`` and the
v1 JSON schema.

Round-trips every serialisable result type, ``GridBreakPoint`` included (R5 #3, plan section
4.2's "JSON envelope"), and checks the error paths that keep a saved score card from silently
becoming a different one: non-finite floats, non-JSON provenance values, an unknown
``schema_version``, and an unknown field. The parity test at the end is what stops the schema --
a second, hand-maintained copy of every field name -- from drifting against the dataclasses it
describes (design choice 6, Phase 3 plan).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable

import jsonschema
import pytest

import marginkit
from marginkit import (
    AdjacentPair,
    Axis,
    Cell,
    Censoring,
    Covariance,
    Definition,
    Diagnostics,
    Fit,
    GridBreakPoint,
    MonotonicityCheck,
    Observations,
    Parameter,
    Ratio,
    Scorecard,
    Status,
    Threshold,
    grid_break_point,
)
from marginkit.report import SCHEMA_VERSION, from_dict, load_schema, to_dict
from marginkit.testing import fake_fit, fake_ratio, fake_threshold

_TAGGED_TYPES: tuple[type, ...] = (Scorecard, GridBreakPoint, Fit, Threshold, Ratio)
_HELPER_TYPES: tuple[type, ...] = (
    Axis,
    Definition,
    Cell,
    Parameter,
    Covariance,
    Diagnostics,
    MonotonicityCheck,
    AdjacentPair,
)


def _grid_result() -> GridBreakPoint:
    return grid_break_point([0.0, 5.0, 10.0], [1.0, 0.95, 0.4], criterion=0.95)


class TestRoundTrip:
    def test_grid_break_point_round_trips(self) -> None:
        result = _grid_result()

        assert from_dict(to_dict(result)) == result

    def test_fit_round_trips(self) -> None:
        fit = fake_fit()

        assert from_dict(to_dict(fit)) == fit

    def test_threshold_round_trips(self) -> None:
        threshold = fake_threshold()

        assert from_dict(to_dict(threshold)) == threshold

    def test_ratio_round_trips(self) -> None:
        ratio = fake_ratio()

        assert from_dict(to_dict(ratio)) == ratio

    def test_scorecard_round_trips(self) -> None:
        card = Scorecard(
            results=(_grid_result(), fake_fit(), fake_threshold(), fake_ratio()),
            provenance={},
        )

        assert from_dict(to_dict(card)) == card


class TestTypeTagging:
    def test_top_level_objects_are_tagged_with_their_class_name(self) -> None:
        assert to_dict(fake_fit())["type"] == "Fit"
        assert to_dict(fake_threshold())["type"] == "Threshold"
        assert to_dict(fake_ratio())["type"] == "Ratio"
        assert to_dict(_grid_result())["type"] == "GridBreakPoint"

    def test_nested_fit_inside_a_threshold_is_also_tagged(self) -> None:
        payload = to_dict(fake_threshold())

        assert payload["fit"]["type"] == "Fit"

    def test_nested_thresholds_inside_a_ratio_are_also_tagged(self) -> None:
        payload = to_dict(fake_ratio())

        assert payload["threshold_a"]["type"] == "Threshold"
        assert payload["threshold_b"]["type"] == "Threshold"

    def test_helper_types_are_not_tagged(self) -> None:
        payload = to_dict(fake_fit())

        assert "type" not in payload["axis"]


class TestEncodingConventions:
    def test_enums_are_written_as_their_string_values(self) -> None:
        payload = to_dict(fake_fit())

        assert payload["status"] == "OK"
        assert isinstance(payload["status"], str)

    def test_tuples_are_written_as_lists(self) -> None:
        payload = to_dict(fake_fit())

        assert isinstance(payload["cells"], list)
        assert isinstance(payload["warnings"], list)


class TestNonFiniteFloatsRaise:
    def test_nan_in_a_result_field_raises(self) -> None:
        result = dataclasses.replace(_grid_result(), max_tested=float("nan"))

        with pytest.raises(ValueError):
            to_dict(result)

    def test_infinity_in_a_result_field_raises(self) -> None:
        result = dataclasses.replace(_grid_result(), max_tested=float("inf"))

        with pytest.raises(ValueError):
            to_dict(result)


class TestNonJsonProvenanceRaises:
    def test_a_tuple_value_in_provenance_raises_type_error(self) -> None:
        result = dataclasses.replace(_grid_result(), provenance={"run": (1, 2)})

        with pytest.raises(TypeError):
            to_dict(result)

    def test_a_set_value_in_provenance_raises_type_error(self) -> None:
        result = dataclasses.replace(_grid_result(), provenance={"run": {1, 2}})

        with pytest.raises(TypeError):
            to_dict(result)

    def test_a_nan_value_in_provenance_raises_value_error(self) -> None:
        result = dataclasses.replace(_grid_result(), provenance={"score": float("nan")})

        with pytest.raises(ValueError):
            to_dict(result)

    def test_json_valued_provenance_is_accepted(self) -> None:
        result = dataclasses.replace(
            _grid_result(), provenance={"run": "abc", "nested": {"k": [1, 2, None, True, 3.5]}}
        )

        payload = to_dict(result)

        assert payload["provenance"]["run"] == "abc"


class TestFromDictErrors:
    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError):
            from_dict({"type": "NotAType", "schema_version": SCHEMA_VERSION})

    def test_unknown_schema_version_raises(self) -> None:
        payload = to_dict(fake_fit())
        payload["schema_version"] = "999"

        with pytest.raises(ValueError):
            from_dict(payload)

    def test_unknown_field_raises(self) -> None:
        payload = to_dict(fake_fit())
        payload["not_a_real_field"] = 1

        with pytest.raises(ValueError):
            from_dict(payload)

    def test_unknown_field_message_names_the_field(self) -> None:
        payload = to_dict(fake_fit())
        payload["not_a_real_field"] = 1

        with pytest.raises(ValueError) as exc_info:
            from_dict(payload)

        assert "not_a_real_field" in str(exc_info.value)

    def test_unknown_field_in_scorecard_message_includes_marginkit_version(self) -> None:
        """Item 3, round 3: for a ``Scorecard`` specifically, an unknown-field error also names
        the version that produced it -- the detail most useful for telling "a newer marginkit
        wrote this" apart from "this file is simply corrupt"."""
        card = Scorecard(results=(_grid_result(),), provenance={}, marginkit_version="9.9.9")
        payload = to_dict(card)
        payload["not_a_real_field"] = 1

        with pytest.raises(ValueError) as exc_info:
            from_dict(payload)

        assert "9.9.9" in str(exc_info.value)

    def test_missing_required_field_raises(self) -> None:
        payload = to_dict(fake_fit())
        del payload["status"]

        with pytest.raises(ValueError):
            from_dict(payload)

    def test_missing_defaulted_field_is_filled_from_its_default(self) -> None:
        payload = to_dict(fake_fit())
        del payload["warnings"]

        rebuilt = from_dict(payload)

        assert rebuilt.warnings == ()


class TestFromDictValidatesNestedTypeTags:
    """Rule 19: ``from_dict`` must check nested ``"type"`` tags too, not just the top-level
    one. ``_threshold_from_dict`` currently calls ``_fit_from_dict`` on the nested ``fit`` dict
    directly, bypassing ``from_dict``'s own top-level dispatch (which is the only place the
    ``"type"`` key is currently read), so a missing or wrong nested tag is silently ignored.
    """

    def test_nested_fit_missing_type_tag_raises(self) -> None:
        payload = to_dict(fake_threshold())
        del payload["fit"]["type"]

        with pytest.raises(ValueError):
            from_dict(payload)

    def test_nested_fit_with_wrong_type_tag_raises(self) -> None:
        payload = to_dict(fake_threshold())
        payload["fit"]["type"] = "Ratio"

        with pytest.raises(ValueError):
            from_dict(payload)


class TestFromDictScorecardRequiresCreatedAtAndVersion:
    """Rule 20: a ``Scorecard`` payload missing ``created_at`` or ``marginkit_version`` must
    raise, rather than silently filling in the dataclass's own ``default_factory`` (today's
    time, the currently-installed version) -- that would invent metadata about a record that
    was actually produced somewhere else, at some other time, by some other version.
    """

    def test_missing_created_at_raises(self) -> None:
        card = Scorecard(results=(_grid_result(),), provenance={})
        payload = to_dict(card)
        del payload["created_at"]

        with pytest.raises(ValueError):
            from_dict(payload)

    def test_missing_marginkit_version_raises(self) -> None:
        card = Scorecard(results=(_grid_result(),), provenance={})
        payload = to_dict(card)
        del payload["marginkit_version"]

        with pytest.raises(ValueError):
            from_dict(payload)


class TestToDictTopLevelTypeRestriction:
    """Rule 21: ``to_dict`` at top level accepts only the five result types -- a helper type
    such as ``Observations`` or ``Axis`` is a dataclass too, so the existing "is a dataclass
    instance" check in ``to_dict`` alone does not exclude it."""

    def test_to_dict_of_observations_raises_type_error(self) -> None:
        axis = Axis(name="noise", unit="m", scale="log")
        obs = Observations.from_counts(
            axis,
            severity=[0.0],
            successes=[1],
            trials=[1],
            outcome="success",
            direction="decreasing",
        )

        with pytest.raises(TypeError):
            to_dict(obs)

    def test_to_dict_of_axis_raises_type_error(self) -> None:
        axis = Axis(name="noise", unit="m", scale="log")

        with pytest.raises(TypeError):
            to_dict(axis)


class TestJsonDumpsSucceedsWithAllowNanFalse:
    @pytest.mark.parametrize(
        "build",
        [fake_fit, fake_threshold, fake_ratio, _grid_result],
    )
    def test_dumps_with_allow_nan_false(self, build: Callable[[], object]) -> None:
        payload = to_dict(build())

        json.dumps(payload, allow_nan=False)


class TestLoadSchema:
    def test_returns_a_dict(self) -> None:
        schema = load_schema()

        assert isinstance(schema, dict)

    def test_is_draft_2020_12(self) -> None:
        schema = load_schema()

        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_root_describes_a_scorecard(self) -> None:
        schema = load_schema()

        assert schema["properties"]["type"]["const"] == "Scorecard"

    def test_defs_holds_every_documented_type(self) -> None:
        schema = load_schema()

        expected = {
            "GridBreakPoint",
            "Fit",
            "Threshold",
            "Ratio",
            "Axis",
            "Definition",
            "Cell",
            "Parameter",
            "Covariance",
        }
        assert expected <= set(schema["$defs"])


class TestSchemaIsStrict:
    """Item 3, round 3: every object in the schema (root and every ``$defs`` entry) sets
    ``"additionalProperties": false``, and v1 is binomial-only, so ``Fit.model``'s enum is
    exactly ``["binomial"]`` -- not just documented as binomial-only by convention."""

    def test_fit_schema_rejects_an_extra_key(self) -> None:
        # decisions/0023 made "diagnostics" a real Fit field (schema v3), so a genuinely-unknown
        # marker key is needed here instead -- "diagnostics" itself would no longer trip this
        # check.
        schema = load_schema()
        validator = jsonschema.Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": "#/$defs/Fit"}
        )
        payload = to_dict(fake_fit())
        payload["not_a_real_field_at_all"] = None

        errors = list(validator.iter_errors(payload))

        assert errors

    def test_fit_model_enum_is_exactly_binomial(self) -> None:
        schema = load_schema()

        assert schema["$defs"]["Fit"]["properties"]["model"]["enum"] == ["binomial"]


class TestSchemaFieldParity:
    """A schema that has drifted from its dataclass is worse than no schema at all."""

    @pytest.mark.parametrize("cls", [GridBreakPoint, Fit, Threshold, Ratio])
    def test_tagged_result_types_match_their_defs_entry(self, cls: type) -> None:
        schema = load_schema()

        field_names = {f.name for f in dataclasses.fields(cls)}
        schema_properties = set(schema["$defs"][cls.__name__]["properties"])

        assert schema_properties == field_names | {"type"}

    @pytest.mark.parametrize(
        "cls",
        [
            Axis,
            Definition,
            Cell,
            Parameter,
            Covariance,
            Diagnostics,
            MonotonicityCheck,
            AdjacentPair,
        ],
    )
    def test_helper_types_match_their_defs_entry_without_a_type_tag(self, cls: type) -> None:
        schema = load_schema()

        field_names = {f.name for f in dataclasses.fields(cls)}
        schema_properties = set(schema["$defs"][cls.__name__]["properties"])

        assert schema_properties == field_names

    def test_root_schema_matches_scorecard_fields(self) -> None:
        schema = load_schema()

        field_names = {f.name for f in dataclasses.fields(Scorecard)}
        schema_properties = set(schema["properties"])

        assert schema_properties == field_names | {"type"}

    def test_root_schema_requires_created_at_and_marginkit_version(self) -> None:
        """Rule 20: the schema's own ``required`` list is the second copy of "these two fields
        must not be silently invented" -- if it drifts from what ``from_dict`` actually
        enforces, a consumer validating against the schema alone would not catch a payload
        ``from_dict`` would reject."""
        schema = load_schema()

        assert "created_at" in schema["required"]
        assert "marginkit_version" in schema["required"]


# ------------------------------------------------------------------------------------------
# Round 4, section 2: counts accept whole-number floats.
# ------------------------------------------------------------------------------------------


class TestFromDictAcceptsWholeNumberFloatCounts:
    """JSON Schema cannot tell ``200.0`` from ``200``, so a ``Cell`` payload with whole-number
    float counts -- exactly what a real ``json.loads`` round-trip of a value written as
    ``200.0`` would produce -- must still load, and load as ``int``."""

    def test_whole_number_float_cell_counts_load_as_int(self) -> None:
        payload = to_dict(fake_fit())
        payload["cells"][0]["successes"] = 200.0
        payload["cells"][0]["trials"] = 200.0

        rebuilt = from_dict(payload)

        assert rebuilt.cells[0].successes == 200
        assert type(rebuilt.cells[0].successes) is int
        assert rebuilt.cells[0].trials == 200
        assert type(rebuilt.cells[0].trials) is int


# ------------------------------------------------------------------------------------------
# Round 4, section 3: schema and from_dict agree.
# ------------------------------------------------------------------------------------------


class TestFitLinkSchemaIsNotNullable:
    """``Fit.link``'s schema enum must not include ``null`` -- ``Fit.__post_init__`` already
    rejects ``link=None`` at runtime (it is not one of the three recognised link names), so the
    schema's ``null`` alternative was never reachable."""

    def test_null_link_is_rejected_by_the_schema(self) -> None:
        schema = load_schema()
        validator = jsonschema.Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": "#/$defs/Fit"}
        )
        payload = to_dict(fake_fit())
        payload["link"] = None

        errors = list(validator.iter_errors(payload))

        assert errors


class TestFitClusterIdsSchemaRequiresUniqueNonEmptyItems:
    """``Fit.cluster_ids``'s schema array adds ``uniqueItems: true`` and ``minItems: 1``; the
    ``null`` alternative (no cluster information recorded) stays valid."""

    def test_empty_cluster_ids_is_rejected_by_the_schema(self) -> None:
        schema = load_schema()
        validator = jsonschema.Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": "#/$defs/Fit"}
        )
        payload = to_dict(fake_fit())
        payload["cluster_ids"] = []

        errors = list(validator.iter_errors(payload))

        assert errors

    def test_duplicate_cluster_ids_is_rejected_by_the_schema(self) -> None:
        schema = load_schema()
        validator = jsonschema.Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": "#/$defs/Fit"}
        )
        payload = to_dict(fake_fit())
        payload["cluster_ids"] = ["a", "a"]

        errors = list(validator.iter_errors(payload))

        assert errors

    def test_null_cluster_ids_is_still_accepted_by_the_schema(self) -> None:
        schema = load_schema()
        validator = jsonschema.Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": "#/$defs/Fit"}
        )
        payload = to_dict(fake_fit())
        payload["cluster_ids"] = None

        errors = list(validator.iter_errors(payload))

        assert not errors


_TAGGED_TYPE_NAMES: tuple[str, ...] = ("Scorecard", "GridBreakPoint", "Fit", "Threshold", "Ratio")


def _as_dict(value: object) -> dict[str, object]:
    """Narrow a schema node read from ``load_schema()`` to a JSON object."""
    assert isinstance(value, dict)
    return value


def _as_str_list(value: object) -> list[str]:
    """Narrow a schema ``required`` list to a list of property names."""
    assert isinstance(value, list) and all(isinstance(item, str) for item in value)
    return value


def _schema_node(type_name: str) -> dict[str, object]:
    schema = load_schema()
    if type_name == "Scorecard":
        return schema
    return _as_dict(_as_dict(schema["$defs"])[type_name])


def _instance_for(type_name: str) -> object:
    if type_name == "Scorecard":
        return Scorecard(results=(_grid_result(),), provenance={})
    if type_name == "GridBreakPoint":
        return _grid_result()
    if type_name == "Fit":
        return fake_fit()
    if type_name == "Threshold":
        return fake_threshold()
    if type_name == "Ratio":
        return fake_ratio()
    raise AssertionError(f"no fake instance builder registered for {type_name!r}")


def _required_key_cases() -> list[tuple[str, str]]:
    return [
        (type_name, key)
        for type_name in _TAGGED_TYPE_NAMES
        for key in _as_str_list(_schema_node(type_name)["required"])
    ]


def _non_required_key_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for type_name in _TAGGED_TYPE_NAMES:
        node = _schema_node(type_name)
        required = set(_as_str_list(node["required"]))
        properties = set(_as_dict(node["properties"]))
        cases.extend((type_name, key) for key in properties - required)
    return cases


class TestFromDictRequiredKeyParityWithSchema:
    """Section 3: for each tagged type, the keys ``from_dict`` requires are *exactly* that
    type's schema ``required`` list -- including the Scorecard's root ``schema_version``, which
    ``from_dict`` must no longer silently fill in from its dataclass default."""

    @pytest.mark.parametrize(("type_name", "key"), _required_key_cases())
    def test_deleting_a_required_key_raises(self, type_name: str, key: str) -> None:
        payload = to_dict(_instance_for(type_name))
        del payload[key]

        with pytest.raises(ValueError):
            from_dict(payload)

    @pytest.mark.parametrize(("type_name", "key"), _non_required_key_cases())
    def test_deleting_a_key_outside_required_still_loads(self, type_name: str, key: str) -> None:
        payload = to_dict(_instance_for(type_name))
        del payload[key]

        from_dict(payload)


# ------------------------------------------------------------------------------------------
# Round 4, section 4: from_dict error ordering and messages.
# ------------------------------------------------------------------------------------------


class TestFromDictChecksSchemaVersionBeforeUnknownFields:
    def test_wrong_schema_version_with_an_extra_key_names_the_version(self) -> None:
        # decisions/0022 made "2" a real, supported schema_version (SCHEMA_VERSION itself), so a
        # genuinely-unrecognised version needs a number outside _SUPPORTED_SCHEMA_VERSIONS --
        # "999" matches TestUnknownSchemaVersion's own choice elsewhere in this file, rather than
        # picking a value that was wrong only by coincidence of when this test was written.
        card = Scorecard(results=(_grid_result(),), provenance={})
        payload = to_dict(card)
        payload["schema_version"] = "999"
        payload["not_a_real_field"] = 1

        with pytest.raises(ValueError) as exc_info:
            from_dict(payload)

        assert "999" in str(exc_info.value)


class TestFromDictNestedUnknownFieldNamesFieldAndBothVersions:
    """An unknown field at any depth inside a ``Scorecard`` -- not only at the top level --
    raises ``ValueError`` naming the field, the card's own ``marginkit_version``, and this
    reader's version."""

    def test_unknown_field_on_a_nested_fit_names_field_and_both_versions(self) -> None:
        # decisions/0023 made "diagnostics" a real Fit field (schema v3): setting it to a value
        # already present under its own default would no longer be an unknown field, so a
        # distinct marker key is used instead.
        card = Scorecard(results=(fake_threshold(),), provenance={}, marginkit_version="9.9.9")
        payload = to_dict(card)
        payload["results"][0]["fit"]["not_a_real_field_at_all"] = None

        with pytest.raises(ValueError) as exc_info:
            from_dict(payload)

        message = str(exc_info.value)
        assert "not_a_real_field_at_all" in message
        assert "9.9.9" in message
        assert marginkit.__version__ in message


# ------------------------------------------------------------------------------------------
# Phase 5, decisions/0010: Threshold.baseline / Threshold.grid, appended fields defaulting to
# None. ``TestSchemaFieldParity`` above already checks that the schema and the dataclass agree
# on field *names*; this section checks that the *values* survive a round trip, and that a card
# written before these two fields existed (no ``baseline``/``grid`` keys at all) still loads.
# ``BaselineRate`` does not exist yet, so it is imported locally inside each test that needs it,
# not at module level -- the same reason every not-yet-existing Phase 5 name in
# ``tests/contract/`` and ``tests/unit/test_censoring.py`` is imported locally: a module-level
# ``ImportError`` here would abort collection of this entire file, not just these tests, taking
# every one of this file's already-passing tests down with it.
# ------------------------------------------------------------------------------------------


class TestThresholdBaselineAndGridRoundTrip:
    def test_fails_at_baseline_threshold_with_baseline_rate_round_trips(self) -> None:
        from marginkit import BaselineRate

        # FAILS_AT_BASELINE places no constraint on fit.status (plan section 5.5, decisions/0008):
        # the control's exact test does not depend on the rest of the curve having converged, so
        # the default (OK) fake fit is a legitimate underlying fit here.
        fit = fake_fit()
        baseline = BaselineRate(
            severity=0.0,
            successes=98,
            trials=200,
            rate=0.49,
            lo=0.4188225152054292,
            hi=0.5614782774378427,
            method="per_cell_clopper_pearson",
        )
        t = Threshold(
            axis=fit.axis,
            definition=Definition.absolute(0.95),
            direction=fit.direction,
            value=None,
            lo=None,
            hi=None,
            level=0.95,
            interval_method="exact_bound",
            censoring=Censoring.NONE,
            status=Status.FAILS_AT_BASELINE,
            dependence="independent",
            fit=fit,
            baseline=baseline,
        )

        rebuilt = from_dict(to_dict(t))

        assert rebuilt == t
        assert rebuilt.baseline == baseline
        assert rebuilt.grid is None

    def test_separation_threshold_with_grid_round_trips(self) -> None:
        fit = fake_fit(status=Status.SEPARATION)
        grid = GridBreakPoint(value=0.05, max_tested=0.1, censoring=Censoring.NONE)
        t = Threshold(
            axis=fit.axis,
            definition=Definition.absolute(0.95),
            direction=fit.direction,
            value=None,
            lo=None,
            hi=None,
            level=0.95,
            interval_method="exact_bound",
            censoring=Censoring.NONE,
            status=Status.SEPARATION,
            dependence="independent",
            fit=fit,
            grid=grid,
        )

        rebuilt = from_dict(to_dict(t))

        assert rebuilt == t
        assert rebuilt.grid == grid
        assert rebuilt.baseline is None

    def test_a_card_written_without_baseline_or_grid_keys_still_loads(self) -> None:
        """Simulates a card written by a marginkit older than Phase 5, before these fields
        existed at all -- not merely a card with ``"baseline": null``, which ``to_dict`` would
        already write for every non-FAILS_AT_BASELINE/non-fallback threshold. Both keys are
        deleted outright, and ``from_dict`` must still load the payload, filling each field from
        the dataclass's own default (``None``), the same way it already does for ``warnings``
        (``TestFromDictErrors::test_missing_defaulted_field_is_filled_from_its_default``).
        """
        payload = to_dict(fake_threshold())
        assert payload["baseline"] is None
        assert payload["grid"] is None
        del payload["baseline"]
        del payload["grid"]

        rebuilt = from_dict(payload)

        assert rebuilt.baseline is None
        assert rebuilt.grid is None


# ------------------------------------------------------------------------------------------
# Phase 7, decisions/0023: Fit.diagnostics, an appended field defaulting to None, serialised
# under schema_version "3". Mirrors TestThresholdBaselineAndGridRoundTrip's own two-test shape:
# a real value round-trips, and a card written before this field existed (no "diagnostics" key
# at all) still loads, filling the dataclass default.
# ------------------------------------------------------------------------------------------


def _sample_diagnostics() -> Diagnostics:
    """``Diagnostics`` is model-only as of decisions/0023's Amendment 1: no ``monotonicity``
    entry here at all (that moved onto ``Fit.monotonicity`` directly -- see
    ``_sample_monotonicity_check`` and ``TestFitMonotonicityRoundTrip`` below)."""
    return Diagnostics(
        deviance=1.23,
        pearson_chi2=1.19,
        df=2,
        dispersion=0.595,
        link_aic={"probit": 10.0, "logit": 10.5, "cloglog": None},
        link_status={
            "probit": Status.OK,
            "logit": Status.OK,
            "cloglog": Status.NOT_CONVERGED,
        },
        warnings=(),
    )


def _v2_shaped_fit_payload() -> dict[str, object]:
    """A ``Fit`` payload shaped like a genuine v2 card: tagged ``schema_version="2"``, with
    *neither* v3-only key present at all -- not merely ``null``, which a fresh v3
    ``to_dict(fake_fit())`` would also produce, but which a real v1/v2 writer never emitted in
    the first place, since the fields did not exist yet.

    Before ``decisions/0023`` Amendment 2 item 4 ("fake_fit mirrors a real fit"), a fresh
    ``fake_fit()`` left both fields ``None`` by default, so the two "written without the key"
    tests below could use a plain ``to_dict(fake_fit())`` and assert ``is None`` first as a
    precondition. Amendment 2 item 4 makes that precondition false: a fresh, ``Status.OK``
    ``fake_fit()`` now always fills both through the real ``diagnose()``/``check_monotonicity()``
    paths. What those two tests actually check -- a key that is *absent* loads as ``None``
    (Appendix B item 4) -- is unchanged and still needs covering, so the base payload here is a
    v2-shaped one instead: downgrading ``schema_version`` alone would not be enough, since
    ``tests/unit/test_schema_rewrite_fidelity.py`` pins that a ``"2"``-tagged ``Fit`` carrying
    either key (even ``null``) is rejected by ``from_dict`` -- so both keys are deleted here,
    not just the one each test is about.
    """
    payload = to_dict(fake_fit())
    payload["schema_version"] = "2"
    del payload["diagnostics"]
    del payload["monotonicity"]
    return payload


class TestFitDiagnosticsRoundTrip:
    def test_fit_with_diagnostics_round_trips(self) -> None:
        diagnostics = _sample_diagnostics()
        fit = fake_fit(diagnostics=diagnostics)

        rebuilt = from_dict(to_dict(fit))

        assert rebuilt == fit
        assert rebuilt.diagnostics == diagnostics

    def test_fit_with_diagnostics_none_round_trips(self) -> None:
        fit = fake_fit(diagnostics=None)

        rebuilt = from_dict(to_dict(fit))

        assert rebuilt == fit
        assert rebuilt.diagnostics is None

    def test_a_fit_written_without_a_diagnostics_key_still_loads(self) -> None:
        """Simulates a card written before this field existed at all (a v2-shaped payload, see
        ``_v2_shaped_fit_payload``): the key is absent outright, and ``from_dict`` must still
        load the payload, filling the dataclass's own default (``None``) -- Appendix B item 4,
        the same pattern as ``Threshold.baseline``/``.grid`` before it.
        """
        payload = _v2_shaped_fit_payload()

        rebuilt = from_dict(payload)

        assert rebuilt.diagnostics is None


# ------------------------------------------------------------------------------------------
# Phase 7, decisions/0023 Amendment 1: Fit.monotonicity, the *last* appended field, populated on
# every fit_dose_response return path (unlike diagnostics, never None for a fresh OK-or-not
# result) but still None on a card read from schema "1" or "2" (Amendment 1, item 8).
# ------------------------------------------------------------------------------------------


def _sample_monotonicity_check() -> MonotonicityCheck:
    return MonotonicityCheck(
        direction="decreasing",
        alpha=0.05,
        dependence="independent",
        method="fisher_exact_one_sided_holm",
        pairs=(
            AdjacentPair(
                severity_low=0.0,
                severity_high=0.01,
                successes_low=57,
                trials_low=200,
                successes_high=143,
                trials_high=300,
                p_value=1.1669624014235122e-05,
                holm_adjusted_p=3.5008872042705366e-05,
                flagged=True,
            ),
        ),
        any_flagged=True,
        warnings=(),
    )


class TestFitMonotonicityRoundTrip:
    def test_fit_with_monotonicity_round_trips(self) -> None:
        monotonicity = _sample_monotonicity_check()
        fit = fake_fit(monotonicity=monotonicity)

        rebuilt = from_dict(to_dict(fit))

        assert rebuilt == fit
        assert rebuilt.monotonicity == monotonicity

    def test_fit_with_an_empty_pairs_tuple_round_trips(self) -> None:
        empty = dataclasses.replace(
            _sample_monotonicity_check(),
            pairs=(),
            any_flagged=False,
            warnings=("fewer than two severity levels",),
        )
        fit = fake_fit(monotonicity=empty)

        rebuilt = from_dict(to_dict(fit))

        assert rebuilt == fit
        assert rebuilt.monotonicity == empty

    def test_fit_with_monotonicity_none_round_trips(self) -> None:
        fit = fake_fit(monotonicity=None)

        rebuilt = from_dict(to_dict(fit))

        assert rebuilt == fit
        assert rebuilt.monotonicity is None

    def test_a_fit_written_without_a_monotonicity_key_still_loads(self) -> None:
        """A card written before this field existed (a v2-shaped payload, see
        ``_v2_shaped_fit_payload`` -- schema "1" or "2", predating even ``diagnostics``): the key
        is absent outright, and ``from_dict`` must still load the payload, filling the dataclass
        default (``None``) -- Amendment 1, item 8."""
        payload = _v2_shaped_fit_payload()

        rebuilt = from_dict(payload)

        assert rebuilt.monotonicity is None
