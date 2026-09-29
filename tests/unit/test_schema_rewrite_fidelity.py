"""api-compat finding 1 (Phase 7 review, folded into
``docs/decisions/0023-fit-diagnostics-and-schema-v3.md``): reading an old card and writing it
back out must reproduce it byte-for-byte, and a card tagged with an old ``schema_version`` must
never be allowed to carry a field that version's schema never had.

Before Amendment 2, ``to_dict`` walked every field of the *current* ``Fit`` dataclass regardless
of the object's own ``schema_version``, so reading a genuine ``"1"``- or ``"2"``-tagged card (one
that never had a ``diagnostics``/``monotonicity`` key at all -- not even as ``null``, since those
fields did not exist when it was written) and writing it back out silently **added** those keys.
That is a real, observable difference in the bytes on disk for a caller who only reads a card and
re-saves it, never touching the objects in between -- exactly the "re-writing an old card" defect
this file pins down. It is a distinct bug from Appendix B's "reading" contract (``from_dict``
already handled a missing key by filling the dataclass default); this is about **writing** an old
object back out.

Mirrors ``tests/unit/test_schema_v3.py``'s own ``_downgrade_schema_version`` helper rather than
introducing a new one.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import jsonschema
import pytest

from marginkit import Scorecard, Status
from marginkit.report import from_dict, load_schema, to_dict
from marginkit.testing import fake_fit, fake_threshold


def _downgrade_schema_version(obj: Any, version: str) -> Any:
    if isinstance(obj, dict):
        return {
            key: (version if key == "schema_version" else _downgrade_schema_version(value, version))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_downgrade_schema_version(item, version) for item in obj]
    return obj


def _old_shaped_scorecard_payload(version: str) -> dict[str, Any]:
    """A payload shaped exactly like a genuine card an old marginkit wrote: every
    ``schema_version`` downgraded, and the v3-only ``Fit`` keys removed *entirely* -- not merely
    set to ``null`` (which ``to_dict`` would also produce for a fresh v3 object, but which a real
    v1/v2 writer never emitted in the first place, since the keys did not exist)."""
    threshold = fake_threshold()
    card = Scorecard(results=(threshold,), provenance={"run": "old"})
    payload = _downgrade_schema_version(to_dict(card), version)
    del payload["results"][0]["fit"]["diagnostics"]
    del payload["results"][0]["fit"]["monotonicity"]
    return payload


class TestRewritingAnOldCardIsByteIdentical:
    @pytest.mark.parametrize("version", ["1", "2"])
    def test_scorecard_threshold_fit_round_trips_byte_identically(self, version: str) -> None:
        payload = _old_shaped_scorecard_payload(version)

        reloaded = from_dict(payload)
        rewritten = to_dict(reloaded)

        assert json.dumps(rewritten, sort_keys=True) == json.dumps(payload, sort_keys=True)

    @pytest.mark.parametrize("version", ["1", "2"])
    def test_rewritten_card_validates_against_its_own_schema_version(self, version: str) -> None:
        payload = _old_shaped_scorecard_payload(version)
        reloaded = from_dict(payload)
        rewritten = to_dict(reloaded)

        schema = load_schema(version)
        jsonschema.Draft202012Validator(schema).validate(rewritten)


class TestOldTaggedFitRejectsNewKeys:
    """A ``"1"``- or ``"2"``-tagged ``Fit`` carrying a ``diagnostics`` or ``monotonicity`` key
    (even a ``null`` one) is not a card that version could ever have produced -- ``from_dict``
    must reject it, not silently accept whichever fields happen to exist on the *current* ``Fit``
    dataclass regardless of the payload's own declared version."""

    @pytest.mark.parametrize("version", ["1", "2"])
    @pytest.mark.parametrize("key", ["diagnostics", "monotonicity"])
    def test_from_dict_rejects_a_null_new_key_on_an_old_tagged_fit(
        self, version: str, key: str
    ) -> None:
        payload = _old_shaped_scorecard_payload(version)
        payload["results"][0]["fit"][key] = None

        with pytest.raises(ValueError):
            from_dict(payload)

    @pytest.mark.parametrize("version", ["1", "2"])
    def test_from_dict_rejects_real_diagnostics_and_monotonicity_on_an_old_tagged_fit(
        self, version: str
    ) -> None:
        """The more realistic case: a genuinely v3-shaped ``Fit`` (real ``diagnostics``/
        ``monotonicity``) mislabelled with an old ``schema_version`` -- ``from_dict`` must still
        refuse it."""
        fit = fake_fit(status=Status.OK)
        assert fit.diagnostics is not None
        assert fit.monotonicity is not None
        threshold = dataclasses.replace(fake_threshold(), fit=fit)
        payload = _downgrade_schema_version(
            to_dict(Scorecard(results=(threshold,), provenance={})), version
        )
        # Deliberately not stripped: both keys stay present with real values.

        with pytest.raises(ValueError):
            from_dict(payload)


class TestFitConstructionRejectsOldSchemaVersionWithNewFields:
    """A ``Fit`` claiming ``schema_version="2"`` (or ``"1"``) while carrying a non-``None``
    ``diagnostics`` or ``monotonicity`` is self-contradictory: that schema version's own document
    has no such field, so an object tagged with it cannot legitimately carry one."""

    def test_schema_version_2_with_diagnostics_set_raises(self) -> None:
        fit = fake_fit(status=Status.OK)
        assert fit.diagnostics is not None

        with pytest.raises(ValueError):
            dataclasses.replace(fit, schema_version="2")

    def test_schema_version_1_with_monotonicity_set_raises(self) -> None:
        fit = fake_fit(status=Status.SEPARATION)
        assert fit.diagnostics is None
        assert fit.monotonicity is not None

        with pytest.raises(ValueError):
            dataclasses.replace(fit, schema_version="1")

    def test_schema_version_2_with_both_none_is_accepted(self) -> None:
        fit = dataclasses.replace(fake_fit(status=Status.SEPARATION), monotonicity=None)
        assert fit.diagnostics is None
        assert fit.monotonicity is None

        replaced = dataclasses.replace(fit, schema_version="2")

        assert replaced.schema_version == "2"

    def test_schema_version_3_with_both_set_is_still_accepted(self) -> None:
        """Sanity check on the fixture itself: the new rule must not accidentally forbid the
        ordinary, current-version case."""
        fit = fake_fit(status=Status.OK)
        assert fit.diagnostics is not None
        assert fit.monotonicity is not None

        assert fit.schema_version == "3"
