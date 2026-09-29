"""Serialisation between marginkit's result dataclasses and JSON: :func:`to_dict`,
:func:`from_dict`, :class:`Scorecard`, and :func:`load_schema`.

``to_dict`` walks a result object and produces a plain, ``json.dumps(..., allow_nan=False)``-safe
structure: enums become their string values, tuples become lists, and :class:`Scorecard`,
:class:`~marginkit.GridBreakPoint`, :class:`~marginkit.Fit`, :class:`~marginkit.Threshold` and
:class:`~marginkit.Ratio` are tagged with a ``"type"`` key naming the class, at every nesting
depth (a ``Fit`` embedded in a ``Threshold`` is tagged too). The five helper types
(:class:`~marginkit.Axis`, :class:`~marginkit.Definition`, :class:`~marginkit.Cell`,
:class:`~marginkit.Parameter`, :class:`~marginkit.Covariance`) are never tagged. A non-finite
float anywhere raises ``ValueError``, and a ``provenance`` value outside plain JSON (a tuple or
a set, for example) raises ``TypeError`` -- no NaN and nothing un-JSON-encodable ever reaches
``json.dumps``.

``from_dict`` is the inverse: it dispatches on ``"type"``, rebuilds nested objects, and raises
``ValueError`` naming the problem. At each level, ``schema_version`` (when the type has one) is
checked before an unknown field is: an unrecognised ``schema_version`` is reported on its own
even if the same dict also carries an unknown field. An unknown field found anywhere inside a
``Scorecard`` -- at the ``Scorecard``'s own level or at any nesting depth beneath it -- names
the field, the enclosing card's ``marginkit_version``, and this reader's version; a bare
``Fit``/``Threshold``/``Ratio``/``GridBreakPoint`` read on its own (not nested in a
``Scorecard``) gets a plainer message with no version context, since there is no card to name.
A key that a tagged type's schema ``required`` list requires but the dict omits raises; a key
the schema does not require, if omitted, is filled from the dataclass's own default. This
required-key set is read from the packaged schema matching the dict's own ``schema_version``
(:data:`load_schema`), not duplicated as a literal list, so it cannot drift from
``schema/scorecard-v{version}.json``.

``SCHEMA_VERSION`` is ``"3"`` as of `decisions/0023` (:class:`~marginkit.Fit` gained
``diagnostics`` and ``monotonicity``; `decisions/0022` had already spent ``"2"`` on
:class:`~marginkit.IntervalShape` gaining ``HALF_OPEN``). ``from_dict`` also still reads ``"1"``
and ``"2"`` cards (Appendix B item 4): ``"1"``, ``"2"`` and ``"3"`` are all accepted
``schema_version`` values, and a freshly-constructed result carries whatever its dataclass field
defaults to, which is ``"3"`` everywhere as of this release.

``load_schema`` reads the packaged ``schema/scorecard-v{version}.json`` with
:mod:`importlib.resources` -- ``schema/scorecard-v1.json`` stays packaged alongside
``scorecard-v2.json`` so a ``"1"``-tagged object's required-field set is checked against the v1
document rather than the current one. **Caveat:** the packaged ``scorecard-v1.json`` is not
byte-identical to the one ``v0.1.0a2`` shipped -- Phase 5 added ``Threshold.baseline`` and
``.grid`` to it while ``schema_version`` was still ``"1"`` -- so "the schema it was written
under" holds for the *current* v1 document, not for every card a ``"1"`` tag has ever described
(`REVIEWS.md` R9). Nothing under ``src/`` imports ``jsonschema``; it stays a
dev-only dependency used by consumers' own validators and by this package's own tests.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Any

from marginkit.empirical import BaselineRate, GridBreakPoint
from marginkit.models import _PRE_DIAGNOSTICS_SCHEMA_VERSIONS, Covariance, Fit, Parameter
from marginkit.ratio import Ratio
from marginkit.threshold import Threshold
from marginkit.types import Axis, Cell, Censoring, Definition, IntervalShape, JSONValue, Status
from marginkit.validation import AdjacentPair, Diagnostics, MonotonicityCheck

__all__ = ["SCHEMA_VERSION", "Scorecard", "from_dict", "load_schema", "to_dict"]

SCHEMA_VERSION = "3"

# Appendix B item 4: `from_dict` must still read the previous schema version after a bump.
# `"1"` predates `decisions/0022` (no `IntervalShape.HALF_OPEN`); `"2"` predates `decisions/0023`
# (no `Fit.diagnostics`/`.monotonicity`); `"3"` is current. A future bump extends this set and
# drops the oldest entry only when that version's reader support is deliberately retired, not
# silently.
_SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1", "2", "3"})


def _default_created_at() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _default_marginkit_version() -> str:
    # Imported lazily, not at module level, to avoid a circular import between this module and
    # marginkit/__init__.py (which imports result types report.py also imports).
    import marginkit

    return marginkit.__version__


@dataclass(frozen=True, kw_only=True)
class Scorecard:
    """A collection of results, plus the metadata that lets a saved file be read back years
    later: which marginkit version produced it, when, and under what schema.

    Attributes
    ----------
    results
        A tuple of results, each a :class:`~marginkit.GridBreakPoint`, :class:`~marginkit.Fit`,
        :class:`~marginkit.Threshold` or :class:`~marginkit.Ratio`. Any other element type
        raises ``TypeError``.
    provenance
        An opaque mapping the caller may attach to record where the run came from. marginkit
        stores it and never interprets it. Empty by default.
    created_at
        An ISO-8601 datetime string carrying a timezone. Defaults to now, in UTC. A given value
        that :func:`datetime.datetime.fromisoformat` cannot parse, or that carries no timezone,
        raises ``ValueError``.
    marginkit_version
        The version of marginkit that produced this scorecard. Defaults to
        :data:`marginkit.__version__` at construction time.
    schema_version
        The serialised-result schema version this object belongs to. Defaults to ``"3"``
        (`decisions/0023`); ``from_dict`` still reads ``"1"`` and ``"2"`` cards.
    """

    results: tuple[GridBreakPoint | Fit | Threshold | Ratio, ...]
    provenance: Mapping[str, JSONValue] = field(default_factory=dict)
    created_at: str = field(default_factory=_default_created_at)
    marginkit_version: str = field(default_factory=_default_marginkit_version)
    schema_version: str = "3"

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(self.results))
        for item in self.results:
            if not isinstance(item, (GridBreakPoint, Fit, Threshold, Ratio)):
                raise TypeError(
                    "Scorecard.results entries must each be a GridBreakPoint, Fit, Threshold "
                    f"or Ratio, got {type(item).__name__}"
                )
        try:
            parsed = dt.datetime.fromisoformat(self.created_at)
        except ValueError as exc:
            raise ValueError(
                f"Scorecard.created_at must be an ISO-8601 datetime string, got {self.created_at!r}"
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError(f"Scorecard.created_at must carry a timezone, got {self.created_at!r}")


_TAGGED_CLASSES: tuple[type, ...] = (Scorecard, GridBreakPoint, Fit, Threshold, Ratio)


# --------------------------------------------------------------------------------------------
# to_dict
# --------------------------------------------------------------------------------------------


def _encode_json_value(value: object) -> JSONValue:
    """Encode a value that must already be plain JSON (a ``provenance`` entry): only
    ``None``/``bool``/``int``/``float``/``str``/``list``/``dict`` are accepted. A tuple, a set,
    or any other type raises ``TypeError``; a non-finite float raises ``ValueError``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float in provenance: {value!r}")
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [_encode_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _encode_json_value(v) for k, v in value.items()}
    raise TypeError(
        "provenance values must be JSON (dict, list, str, int, float, bool or None), got "
        f"{type(value).__name__}: {value!r}"
    )


def _encode_provenance(value: Mapping[str, object]) -> dict[str, JSONValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"provenance must be a mapping, got {type(value).__name__}")
    return {str(k): _encode_json_value(v) for k, v in value.items()}


def _encode_field_value(value: object) -> JSONValue:
    if isinstance(value, (Censoring, Status, IntervalShape)):
        return value.value
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float in result: {value!r}")
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    if value is None:
        return None
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _encode_dataclass_instance(value)
    if isinstance(value, (tuple, list)):
        return [_encode_field_value(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _encode_field_value(v) for k, v in value.items()}
    raise TypeError(f"cannot encode value of type {type(value).__name__}: {value!r}")


def _encode_dataclass_instance(obj: Any) -> dict[str, JSONValue]:
    cls = type(obj)
    # api-compat finding 1 (decisions/0023 Amendment 2): a Fit tagged "1" or "2" never had a
    # diagnostics/monotonicity key at all -- not even as null -- so re-writing one must not
    # silently add either key just because the *current* Fit dataclass carries the field.
    # Fit.__post_init__ already requires both to be None whenever schema_version predates them
    # (_PRE_DIAGNOSTICS_SCHEMA_VERSIONS), so omitting the keys here loses no information.
    omitted_fields: frozenset[str] = (
        frozenset({"diagnostics", "monotonicity"})
        if isinstance(obj, Fit) and obj.schema_version in _PRE_DIAGNOSTICS_SCHEMA_VERSIONS
        else frozenset()
    )
    result: dict[str, JSONValue] = {}
    for f in dataclasses.fields(obj):
        if f.name in omitted_fields:
            continue
        raw = getattr(obj, f.name)
        if f.name == "provenance":
            result[f.name] = _encode_provenance(raw)
        else:
            result[f.name] = _encode_field_value(raw)
    if cls in _TAGGED_CLASSES:
        result["type"] = cls.__name__
    return result


def to_dict(obj: object) -> dict[str, JSONValue]:
    """Encode a marginkit result dataclass instance into a plain, JSON-safe dict.

    Parameters
    ----------
    obj
        A :class:`Scorecard`, :class:`~marginkit.GridBreakPoint`, :class:`~marginkit.Fit`,
        :class:`~marginkit.Threshold` or :class:`~marginkit.Ratio` instance -- the five tagged
        types. Nothing else is accepted at the top level (a helper type such as
        :class:`~marginkit.Axis` only ever appears nested inside one of these).

    Returns
    -------
    dict[str, JSONValue]
        A dict safe to pass to ``json.dumps(..., allow_nan=False)``. Tagged types carry a
        ``"type"`` key naming the class, at every nesting depth.

    Raises
    ------
    ValueError
        If any float anywhere in ``obj`` (including inside ``provenance``) is NaN or infinite.
    TypeError
        If ``obj`` is not one of the five tagged types, or if a ``provenance`` value is not
        plain JSON.
    """
    if not isinstance(obj, _TAGGED_CLASSES):
        raise TypeError(
            "to_dict expects a Scorecard, GridBreakPoint, Fit, Threshold or Ratio instance, "
            f"got {type(obj).__name__}"
        )
    return _encode_dataclass_instance(obj)


# --------------------------------------------------------------------------------------------
# from_dict
# --------------------------------------------------------------------------------------------


@lru_cache(maxsize=8)  # generous headroom for however many schema versions are ever supported
def _schema_required_by_type(version: str = SCHEMA_VERSION) -> dict[str, frozenset[str]]:
    """The packaged ``version`` schema's own ``required`` list for each of the five tagged
    result types (:class:`Scorecard`, :class:`~marginkit.GridBreakPoint`,
    :class:`~marginkit.Fit`, :class:`~marginkit.Threshold`, :class:`~marginkit.Ratio`), keyed by
    class name, with ``"type"`` removed -- ``from_dict`` checks ``"type"`` itself, separately.

    Read from :func:`load_schema` rather than duplicated as a literal list, so a required field
    can never drift between the schema and ``from_dict`` without ``TestSchemaFieldParity`` (or
    this function's own malformed-schema check) catching it (round 4 section 3). Parametrised on
    ``version`` (rather than always reading the current schema) so a ``"1"``-tagged object read
    through :func:`from_dict` is checked against the v1 document rather than the current one --
    required fields happen to be identical between ``"1"`` and ``"2"`` today (`decisions/0022`
    only widened an enum), but this does not assume that stays true. Note the v1 document was
    itself amended in place after ``v0.1.0a2`` was tagged (`REVIEWS.md` R9), so it is the current
    v1 schema, not a frozen historical one.
    """
    schema = load_schema(version)
    root_required = schema.get("required")
    if not isinstance(root_required, list):
        raise TypeError(
            f"marginkit's packaged schema v{version} is malformed: missing root 'required'"
        )
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        raise TypeError(f"marginkit's packaged schema v{version} is malformed: missing '$defs'")

    result: dict[str, frozenset[str]] = {
        "Scorecard": frozenset(str(k) for k in root_required if k != "type")
    }
    for name in ("GridBreakPoint", "Fit", "Threshold", "Ratio"):
        node = defs.get(name)
        if not isinstance(node, dict):
            raise TypeError(
                f"marginkit's packaged schema v{version} is malformed: missing '$defs.{name}'"
            )
        node_required = node.get("required")
        if not isinstance(node_required, list):
            raise TypeError(
                f"marginkit's packaged schema v{version} is malformed: missing "
                f"'$defs.{name}.required'"
            )
        result[name] = frozenset(str(k) for k in node_required if k != "type")
    return result


@lru_cache(maxsize=8)  # generous headroom for however many schema versions are ever supported
def _schema_properties_by_type(version: str = SCHEMA_VERSION) -> dict[str, frozenset[str]]:
    """The packaged ``version`` schema's own ``properties`` key set for each of the five tagged
    result types, keyed by class name, ``"type"`` **included** (unlike
    :func:`_schema_required_by_type`, which strips it since ``from_dict`` checks ``"type"``
    separately -- there is no such special-casing needed here).

    Used as :func:`_validated_fields`'s "allowed keys" set for a tagged type, in place of the
    *current* dataclass's own field names: a key that a tagged object's own ``schema_version``
    never had is then rejected as unknown even when the *current* dataclass does have that field
    (api-compat finding 1, `decisions/0023` Amendment 2: a ``"1"``- or ``"2"``-tagged ``Fit``
    payload carrying ``diagnostics``/``monotonicity`` -- fields schema ``"3"`` alone added -- must
    be rejected, not silently accepted because today's ``Fit`` dataclass happens to have them).
    Same caching and malformed-schema-detection shape as :func:`_schema_required_by_type`, read
    from :func:`load_schema` rather than duplicated as a literal list.
    """
    schema = load_schema(version)
    root_properties = schema.get("properties")
    if not isinstance(root_properties, dict):
        raise TypeError(
            f"marginkit's packaged schema v{version} is malformed: missing root 'properties'"
        )
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        raise TypeError(f"marginkit's packaged schema v{version} is malformed: missing '$defs'")

    result: dict[str, frozenset[str]] = {"Scorecard": frozenset(str(k) for k in root_properties)}
    for name in ("GridBreakPoint", "Fit", "Threshold", "Ratio"):
        node = defs.get(name)
        if not isinstance(node, dict):
            raise TypeError(
                f"marginkit's packaged schema v{version} is malformed: missing '$defs.{name}'"
            )
        node_properties = node.get("properties")
        if not isinstance(node_properties, dict):
            raise TypeError(
                f"marginkit's packaged schema v{version} is malformed: missing "
                f"'$defs.{name}.properties'"
            )
        result[name] = frozenset(str(k) for k in node_properties)
    return result


def _validated_fields(
    cls: type, data: object, *, tagged: bool, card_version: str | None = None
) -> dict[str, Any]:
    """Check ``data``'s keys against ``cls``'s dataclass fields (and ``schema_version``, if
    ``cls`` has one), and return the subset of ``data`` corresponding to fields that are
    present.

    ``schema_version`` is checked before the unknown-field check, so an unsupported version is
    reported on its own even when the dict also carries an unknown key -- against
    :data:`_SUPPORTED_SCHEMA_VERSIONS`, not just the current :data:`SCHEMA_VERSION` (Appendix B
    item 4: a card written under the previous version must still read). ``card_version`` is the
    ``marginkit_version`` of the enclosing :class:`Scorecard`, threaded down from
    :func:`from_dict` for every object nested inside one; when it is not ``None``, an
    unknown-field error names it (and this reader's version) alongside the field. A bare
    ``Fit``/``Threshold``/``Ratio``/``GridBreakPoint`` read on its own (``card_version=None``)
    gets a plainer message, since there is no card to name.

    For one of the five tagged result types, a field is required exactly when the packaged
    schema matching the dict's own ``schema_version`` says so
    (:func:`_schema_required_by_type`); for an untagged helper type (:class:`~marginkit.Axis`,
    :class:`~marginkit.Definition`, :class:`~marginkit.Cell`, :class:`~marginkit.Parameter`,
    :class:`~marginkit.Covariance`), a field is required exactly when its dataclass field has no
    default. A required field missing from ``data`` raises ``ValueError``; every other missing
    field is simply omitted here, so the constructor applies its own default.
    """
    if not isinstance(data, Mapping):
        raise ValueError(
            f"from_dict: expected a mapping for {cls.__name__}, got {type(data).__name__}"
        )

    fields = dataclasses.fields(cls)
    field_names = {f.name for f in fields}

    schema_version = SCHEMA_VERSION
    if "schema_version" in field_names:
        schema_version = data.get("schema_version", SCHEMA_VERSION)
        if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"from_dict: unknown schema_version {schema_version!r} for {cls.__name__}, "
                f"expected one of {sorted(_SUPPORTED_SCHEMA_VERSIONS)!r}"
            )

    # A tagged type's allowed keys come from *that version's own packaged schema*, not from the
    # current dataclass's field names (api-compat finding 1, `decisions/0023` Amendment 2): a
    # `"1"`- or `"2"`-tagged `Fit` payload carrying `diagnostics`/`monotonicity` -- fields that
    # version's own schema document never had -- must be rejected as unknown, even though the
    # *current* `Fit` dataclass does have those fields. An untagged helper type has no per-version
    # schema entry of its own to check against (it is never in `_SUPPORTED_SCHEMA_VERSIONS`'
    # version history independently), so it still allows exactly its current dataclass fields.
    allowed = _schema_properties_by_type(schema_version)[cls.__name__] if tagged else field_names

    unknown = set(data) - allowed
    if unknown:
        if card_version is not None:
            reader_version = _default_marginkit_version()
            raise ValueError(
                f"from_dict: unknown field(s) {sorted(unknown)} for {cls.__name__} (card "
                f"written by marginkit {card_version}; this reader is marginkit "
                f"{reader_version})"
            )
        raise ValueError(f"from_dict: unknown field(s) {sorted(unknown)} for {cls.__name__}")

    required = (
        _schema_required_by_type(schema_version)[cls.__name__]
        if tagged
        else frozenset(
            f.name
            for f in fields
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        )
    )

    result: dict[str, Any] = {}
    for f in fields:
        if f.name in data:
            result[f.name] = data[f.name]
        elif f.name in required:
            raise ValueError(f"from_dict: missing required field {f.name!r} for {cls.__name__}")
        else:
            continue
    return result


def _expect_tag(data: object, *, expected: str) -> object:
    """Check that a nested tagged value carries ``"type": expected`` before it is rebuilt.

    A wrong or missing ``"type"`` on a nested value (for example a ``Threshold`` payload where
    ``Ratio.threshold_a`` expects a ``Threshold``) is a corrupted or hand-edited file, not
    something to coerce silently.
    """
    if not isinstance(data, Mapping):
        raise ValueError(
            f"from_dict: expected a mapping tagged type={expected!r}, got {type(data).__name__}"
        )
    tag = data.get("type")
    if tag != expected:
        raise ValueError(f"from_dict: expected type={expected!r}, got {tag!r}")
    return data


def _axis_from_dict(data: object, card_version: str | None) -> Axis:
    return Axis(**_validated_fields(Axis, data, tagged=False, card_version=card_version))


def _definition_from_dict(data: object, card_version: str | None) -> Definition:
    fields = _validated_fields(Definition, data, tagged=False, card_version=card_version)
    return Definition(**fields)


def _cell_from_dict(data: object, card_version: str | None) -> Cell:
    return Cell(**_validated_fields(Cell, data, tagged=False, card_version=card_version))


def _parameter_from_dict(data: object, card_version: str | None) -> Parameter:
    return Parameter(**_validated_fields(Parameter, data, tagged=False, card_version=card_version))


def _covariance_from_dict(data: object, card_version: str | None) -> Covariance:
    fields = _validated_fields(Covariance, data, tagged=False, card_version=card_version)
    return Covariance(**fields)


def _adjacent_pair_from_dict(data: object, card_version: str | None) -> AdjacentPair:
    """``AdjacentPair`` is an untagged helper, like ``Cell`` and ``Parameter``: it only ever
    appears inside ``MonotonicityCheck.pairs``, never as a card's top-level result.
    """
    fields = _validated_fields(AdjacentPair, data, tagged=False, card_version=card_version)
    return AdjacentPair(**fields)


def _monotonicity_check_from_dict(data: object, card_version: str | None) -> MonotonicityCheck:
    """``MonotonicityCheck`` is an untagged helper, like ``BaselineRate``: it only ever appears
    as ``Fit.monotonicity`` (`decisions/0023` "Amendment 1").
    """
    fields = _validated_fields(MonotonicityCheck, data, tagged=False, card_version=card_version)
    fields["pairs"] = tuple(_adjacent_pair_from_dict(p, card_version) for p in fields["pairs"])
    return MonotonicityCheck(**fields)


def _diagnostics_from_dict(data: object, card_version: str | None) -> Diagnostics:
    """``Diagnostics`` is an untagged helper, like ``BaselineRate``: it only ever appears as
    ``Fit.diagnostics`` (`decisions/0023`).
    """
    fields = _validated_fields(Diagnostics, data, tagged=False, card_version=card_version)
    fields["link_status"] = {k: Status(v) for k, v in fields["link_status"].items()}
    return Diagnostics(**fields)


def _fit_from_dict(data: object, card_version: str | None) -> Fit:
    fields = _validated_fields(Fit, data, tagged=True, card_version=card_version)
    fields["axis"] = _axis_from_dict(fields["axis"], card_version)
    fields["cells"] = tuple(_cell_from_dict(c, card_version) for c in fields["cells"])
    fields["status"] = Status(fields["status"])
    if fields.get("params") is not None:
        fields["params"] = {
            k: _parameter_from_dict(v, card_version) for k, v in fields["params"].items()
        }
    if fields.get("covariance") is not None:
        fields["covariance"] = _covariance_from_dict(fields["covariance"], card_version)
    if fields.get("cluster_ids") is not None:
        fields["cluster_ids"] = tuple(fields["cluster_ids"])
    # `diagnostics`/`monotonicity` are the appended fields of `decisions/0023` (Amendment 1 for
    # the latter). `_validated_fields` fills a key a card omits from the dataclass default
    # (`None`), so a card written before this phase decodes with both `None` and needs no
    # special case beyond the nested-object conversion below.
    if fields.get("diagnostics") is not None:
        fields["diagnostics"] = _diagnostics_from_dict(fields["diagnostics"], card_version)
    if fields.get("monotonicity") is not None:
        fields["monotonicity"] = _monotonicity_check_from_dict(fields["monotonicity"], card_version)
    return Fit(**fields)


def _baseline_rate_from_dict(data: object, card_version: str | None) -> BaselineRate:
    """``BaselineRate`` is an untagged helper, like ``Cell`` and ``Parameter``: it only ever
    appears as ``Threshold.baseline``, never as a card's top-level result, so it carries no
    ``"type"`` discriminator.
    """
    fields = _validated_fields(BaselineRate, data, tagged=False, card_version=card_version)
    return BaselineRate(**fields)


def _threshold_from_dict(data: object, card_version: str | None) -> Threshold:
    fields = _validated_fields(Threshold, data, tagged=True, card_version=card_version)
    fields["axis"] = _axis_from_dict(fields["axis"], card_version)
    fields["definition"] = _definition_from_dict(fields["definition"], card_version)
    fields["censoring"] = Censoring(fields["censoring"])
    fields["status"] = Status(fields["status"])
    fields["fit"] = _fit_from_dict(_expect_tag(fields["fit"], expected="Fit"), card_version)
    # `baseline` and `grid` are the appended fields of `decisions/0010`. `_validated_fields`
    # fills a key a card omits from the dataclass default, so a card written before Phase 5
    # decodes with both `None` and needs no special case here.
    if fields.get("baseline") is not None:
        fields["baseline"] = _baseline_rate_from_dict(fields["baseline"], card_version)
    if fields.get("grid") is not None:
        fields["grid"] = _grid_break_point_from_dict(
            _expect_tag(fields["grid"], expected="GridBreakPoint"), card_version
        )
    return Threshold(**fields)


def _ratio_from_dict(data: object, card_version: str | None) -> Ratio:
    fields = _validated_fields(Ratio, data, tagged=True, card_version=card_version)
    fields["threshold_a"] = _threshold_from_dict(
        _expect_tag(fields["threshold_a"], expected="Threshold"), card_version
    )
    fields["threshold_b"] = _threshold_from_dict(
        _expect_tag(fields["threshold_b"], expected="Threshold"), card_version
    )
    if fields.get("shape") is not None:
        fields["shape"] = IntervalShape(fields["shape"])
    fields["censoring"] = Censoring(fields["censoring"])
    fields["status"] = Status(fields["status"])
    return Ratio(**fields)


def _grid_break_point_from_dict(data: object, card_version: str | None) -> GridBreakPoint:
    fields = _validated_fields(GridBreakPoint, data, tagged=True, card_version=card_version)
    fields["censoring"] = Censoring(fields["censoring"])
    return GridBreakPoint(**fields)


def _scorecard_from_dict(data: object, card_version: str | None) -> Scorecard:
    # ``card_version`` (uniform with every other builder in _RESULT_BUILDERS) is unused here: a
    # Scorecard is always the root of its own tree, never nested inside another Scorecard, so
    # its own marginkit_version is what every unknown-field error beneath it names instead.
    if not isinstance(data, Mapping):
        raise ValueError(f"from_dict: expected a mapping for Scorecard, got {type(data).__name__}")
    own_version = data.get("marginkit_version")
    own_version_str = own_version if isinstance(own_version, str) else "<unknown>"
    fields = _validated_fields(Scorecard, data, tagged=True, card_version=own_version_str)
    fields["results"] = tuple(
        _from_dict_impl(item, card_version=own_version_str) for item in fields["results"]
    )
    return Scorecard(**fields)


_RESULT_BUILDERS: dict[str, Any] = {
    "GridBreakPoint": _grid_break_point_from_dict,
    "Fit": _fit_from_dict,
    "Threshold": _threshold_from_dict,
    "Ratio": _ratio_from_dict,
    "Scorecard": _scorecard_from_dict,
}


def _from_dict_impl(data: object, *, card_version: str | None) -> object:
    if not isinstance(data, Mapping):
        raise ValueError(f"from_dict expects a mapping, got {type(data).__name__}")
    type_name = data.get("type")
    if type_name is None:
        raise ValueError("from_dict: missing required field 'type'")
    builder = _RESULT_BUILDERS.get(type_name)
    if builder is None:
        raise ValueError(f"from_dict: unknown type {type_name!r}")
    result: object = builder(data, card_version)
    return result


def from_dict(data: object) -> object:
    """Rebuild a marginkit result object from the dict :func:`to_dict` produced (or an
    equivalent one read back through ``json.loads``).

    Parameters
    ----------
    data
        A mapping carrying a ``"type"`` key naming one of ``Scorecard``, ``GridBreakPoint``,
        ``Fit``, ``Threshold`` or ``Ratio``, plus that type's fields.

    Returns
    -------
    object
        An instance of the type named by ``data["type"]``. ``from_dict(to_dict(x)) == x`` for
        every ``x`` of these five types. A ``schema_version`` ``"1"`` or ``"2"`` card (written
        before `decisions/0022`/`decisions/0023` respectively) round-trips too: ``"1"``, ``"2"``
        and ``"3"`` are all accepted (Appendix B item 4); a ``"1"`` card's own ``Ratio.shape`` was
        never ``HALF_OPEN``, and neither a ``"1"`` nor a ``"2"`` card's ``Fit`` ever carried
        ``diagnostics``/``monotonicity`` (both decode as ``None``).

    Raises
    ------
    ValueError
        If ``"type"`` is missing or unrecognised, if ``schema_version`` (at any nesting level)
        is not one of :data:`_SUPPORTED_SCHEMA_VERSIONS`, if a field (at any nesting level) is
        not recognised, or if a required field is missing.
    """
    return _from_dict_impl(data, card_version=None)


# --------------------------------------------------------------------------------------------
# load_schema
# --------------------------------------------------------------------------------------------


def load_schema(version: str = SCHEMA_VERSION) -> dict[str, object]:
    """Load a packaged score-card JSON Schema (draft 2020-12).

    Reads ``schema/scorecard-v{version}.json`` from inside the installed ``marginkit`` package
    using :mod:`importlib.resources`, so it works the same way from a wheel as from a source
    checkout. ``jsonschema`` itself is never imported here or anywhere under ``src/``; it is a
    dev-only dependency for consumers that want to validate against the schema.

    Parameters
    ----------
    version
        Which packaged schema version to load. Defaults to :data:`SCHEMA_VERSION` (the current
        one, ``"3"`` as of `decisions/0023`); ``"1"`` and ``"2"`` are also packaged, so
        ``load_schema("1")``/``load_schema("2")`` read the schema a card written before
        `decisions/0022`/`decisions/0023` respectively was actually validated against.

    Returns
    -------
    dict[str, object]
        The parsed JSON Schema document.

    Raises
    ------
    FileNotFoundError
        If ``version`` names a schema that is not packaged (only :data:`_SUPPORTED_SCHEMA_VERSIONS`
        are).
    """
    text = (
        resources.files("marginkit")
        .joinpath("schema", f"scorecard-v{version}.json")
        .read_text(encoding="utf-8")
    )
    schema: dict[str, object] = json.loads(text)
    return schema
