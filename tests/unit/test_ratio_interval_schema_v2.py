"""``decisions/0022``: ``schema_version`` becomes ``"2"``, and ``HALF_OPEN`` is part of it.

**Update (decisions/0023):** ``SCHEMA_VERSION`` has since been bumped again, to ``"3"``
(``Fit.diagnostics``, ``tests/unit/test_schema_v3.py``). This file's own subject -- ``HALF_OPEN``
validating against the packaged v2 document, and the v1 document staying ignorant of it -- is
unchanged by that bump, so the tests below still assert it; only the *current* ``SCHEMA_VERSION``
a freshly-built object carries has moved from ``"2"`` to ``"3"``.

Four things this file pins down, per Appendix B and the decision's own "Consequences":

1. A `HALF_OPEN` :class:`~marginkit.Ratio` (built through :func:`marginkit.testing.fake_ratio`,
   item 5 of the brief this file was written against) validates against the packaged **v2**
   schema.
2. The **v1** schema, which stays packaged unchanged for the reader path, does not know
   ``HALF_OPEN`` -- a card written before ``0022`` could never have contained one, so the v1
   schema must reject it, not silently accept a shape it predates.
3. A freshly-built card round-trips through JSON at its current ``schema_version`` (``"3"`` as of
   decisions/0023) throughout, ``HALF_OPEN`` included.
4. A card stored under ``schema_version == "1"`` (built here by taking a fresh card and
   recursively downgrading every ``schema_version`` key to ``"1"`` -- the "build one" option
   Appendix B leaves open, chosen over a frozen fixture because there is no genuine historical
   v1 card on disk to freeze: this is the very first version bump this package has made) still
   loads through :func:`marginkit.report.from_dict` without error, and the reloaded object
   preserves ``schema_version == "1"`` rather than being silently upgraded.

Mirrors ``tests/unit/test_report.py``'s own conventions (``jsonschema.Draft202012Validator``
against ``load_schema()``'s ``$defs``, ``to_dict``/``from_dict`` round-trips) rather than
introducing new ones.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import jsonschema
import pytest

from marginkit import IntervalShape, Scorecard, Status, grid_break_point
from marginkit.report import SCHEMA_VERSION, from_dict, load_schema, to_dict
from marginkit.testing import fake_ratio


def _downgrade_schema_version(obj: Any, version: str) -> Any:
    """Recursively replace every ``"schema_version"`` value in a ``to_dict()`` payload -- the
    only way to simulate a card genuinely written under an older version, since every tagged
    type's ``schema_version`` is its own independent field, not inherited from the enclosing
    ``Scorecard``."""
    if isinstance(obj, dict):
        return {
            key: (version if key == "schema_version" else _downgrade_schema_version(value, version))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_downgrade_schema_version(item, version) for item in obj]
    return obj


class TestSchemaVersionIsNowTwo:
    """decisions/0023 has since bumped ``SCHEMA_VERSION`` again, to ``"3"`` (``Fit.diagnostics``)
    -- these assertions now check the *current* value, not literally "two"; this class's own
    name and this file's HALF_OPEN-specific content still document decisions/0022 accurately."""

    def test_schema_version_constant_is_3(self) -> None:
        assert SCHEMA_VERSION == "3"

    def test_a_freshly_built_ratio_defaults_to_schema_version_3(self) -> None:
        assert fake_ratio().schema_version == "3"


class TestFakeRatioBuildsAGenuineHalfOpenResult:
    """Item 5 of the brief this file was written against: ``fake_ratio`` must be able to build a
    ``HALF_OPEN`` result whose *fields*, not only its schema validity, actually match
    ``decisions/0022``'s semantics -- ``lo`` set, ``hi`` is ``None``, ``lo <= estimate``. A
    generic parametrised sweep over every ``IntervalShape`` already exists
    (``tests/unit/test_testing.py``'s ``TestFakeRatioSatisfiesOkNoneInvariants``), but it only
    checks the estimate/threshold-value relationship shared by every shape, not this shape's own
    ``hi is None`` invariant -- asserted directly here instead of assumed covered."""

    def test_half_open_fake_has_hi_none_and_lo_at_or_below_estimate(self) -> None:
        ratio = fake_ratio(shape=IntervalShape.HALF_OPEN, status=Status.OK)

        assert ratio.shape is IntervalShape.HALF_OPEN
        assert ratio.lo is not None
        assert ratio.hi is None
        assert ratio.estimate is not None
        assert ratio.lo <= ratio.estimate


class TestHalfOpenRatioValidatesAgainstTheV2Schema:
    def test_half_open_ratio_has_no_schema_errors_under_v2(self) -> None:
        ratio = fake_ratio(shape=IntervalShape.HALF_OPEN, status=Status.OK)
        # decisions/0023 bumped SCHEMA_VERSION again, to "3": this now loads the current (v3)
        # schema, which still carries HALF_OPEN unchanged from v2.
        schema = load_schema()
        validator = jsonschema.Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": "#/$defs/Ratio"}
        )
        payload = to_dict(ratio)

        errors = list(validator.iter_errors(payload))

        assert errors == []

    def test_half_open_is_in_the_v2_intervalshape_enum(self) -> None:
        schema = load_schema()

        assert "HALF_OPEN" in schema["$defs"]["IntervalShape"]["enum"]


class TestHalfOpenIsUnknownToTheV1Schema:
    """The v1 schema stays packaged, unchanged, for the reader path (`decisions/0022`'s
    Consequences) -- it must not have quietly grown ``HALF_OPEN`` too, since no card tagged
    ``schema_version: "1"`` could ever have contained one."""

    def test_half_open_is_not_in_the_v1_intervalshape_enum(self) -> None:
        schema_v1 = load_schema(version="1")

        assert "HALF_OPEN" not in schema_v1["$defs"]["IntervalShape"]["enum"]

    def test_half_open_ratio_is_rejected_by_the_v1_schema(self) -> None:
        ratio = fake_ratio(shape=IntervalShape.HALF_OPEN, status=Status.OK)
        schema_v1 = load_schema(version="1")
        validator = jsonschema.Draft202012Validator(
            {"$defs": schema_v1["$defs"], "$ref": "#/$defs/Ratio"}
        )
        payload = to_dict(ratio)

        errors = list(validator.iter_errors(payload))

        assert errors


class TestV2CardRoundTripsWithAHalfOpenRatio:
    def test_card_round_trips_through_json_text_at_schema_version_2(self) -> None:
        card = Scorecard(
            results=(fake_ratio(shape=IntervalShape.HALF_OPEN, status=Status.OK),),
            provenance={},
        )

        payload = to_dict(card)
        text = json.dumps(payload)
        reloaded = from_dict(json.loads(text))

        assert reloaded == card
        # decisions/0023 bumped SCHEMA_VERSION again, to "3"; a freshly-built card now carries
        # that value throughout, HALF_OPEN included.
        assert payload["schema_version"] == "3"
        assert payload["results"][0]["schema_version"] == "3"


class TestV1CardStillLoads:
    """A card genuinely written under ``schema_version == "1"`` -- simulated by downgrading a
    fresh card's own ``schema_version`` fields, per this file's module docstring -- must still
    load through ``from_dict`` (Appendix B), and the reloaded objects must preserve ``"1"``
    rather than being silently rewritten to the current version.

    Uses ``grid_break_point`` (module docstring's simplicity note): it has no nested tagged
    sub-objects, so the "expected" comparison object is a single ``dataclasses.replace`` away,
    unlike a ``Ratio`` (which nests ``Threshold``, which nests ``Fit``, each an independent
    ``schema_version``).
    """

    def test_a_downgraded_v1_grid_result_card_loads_and_keeps_version_1(self) -> None:
        grid = grid_break_point([0.0, 5.0, 10.0], [1.0, 0.95, 0.4], criterion=0.95)
        # decisions/0023 bumped SCHEMA_VERSION again, to "3": freshly built, confirms the
        # downgrade below is real.
        assert grid.schema_version == "3"
        card = Scorecard(results=(grid,), provenance={})

        payload = to_dict(card)
        v1_payload = _downgrade_schema_version(payload, "1")
        reloaded = from_dict(json.loads(json.dumps(v1_payload)))

        assert isinstance(reloaded, Scorecard)
        assert reloaded.schema_version == "1"
        assert reloaded.results[0].schema_version == "1"

        expected_grid = dataclasses.replace(grid, schema_version="1")
        expected_card = dataclasses.replace(card, schema_version="1", results=(expected_grid,))
        assert reloaded == expected_card

    def test_v1_payload_schema_version_999_still_raises(self) -> None:
        """Sanity check on the downgrade helper itself: a version outside
        ``_SUPPORTED_SCHEMA_VERSIONS`` (``{"1", "2", "3"}`` as of decisions/0023) must still be
        rejected -- accepting "1" is a deliberate widening, not "any string goes"."""
        grid = grid_break_point([0.0, 5.0, 10.0], [1.0, 0.95, 0.4], criterion=0.95)
        card = Scorecard(results=(grid,), provenance={})
        payload = to_dict(card)
        bad_payload = _downgrade_schema_version(payload, "999")

        with pytest.raises(ValueError):
            from_dict(json.loads(json.dumps(bad_payload)))
