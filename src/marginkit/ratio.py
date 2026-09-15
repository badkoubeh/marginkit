"""The ratio-of-two-thresholds result and its interval-shape invariants (§5.6).

As of ``0.1.0a2`` this module holds only :class:`Ratio`. Computing a ratio (``ratio_interval()``,
plan §4, §5.6) is Phase 6 work and is not part of this release: there is no way to produce a
non-fake :class:`Ratio` yet, only to construct one directly or via
:func:`marginkit.testing.fake_ratio`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from marginkit.threshold import Threshold
from marginkit.types import Censoring, IntervalShape, JSONValue, Status, _check_finite_number

__all__ = ["Ratio"]

_VALID_METHODS = frozenset({"fieller", "log_delta"})
_VALID_DEPENDENCE = frozenset({"independent"})


def _check_finite(value: float | None, *, label: str) -> None:
    if value is not None:
        _check_finite_number(value, label=f"Ratio.{label}")


@dataclass(frozen=True, kw_only=True)
class Ratio:
    """The ratio of two thresholds' severities, on the same axis, with a confidence interval.

    A Fieller-type interval is not always a single bounded interval (§5.6): ``shape`` records
    which geometry ``lo``/``hi`` describe, and that geometry is never clipped to look bounded
    when it isn't.

    **A failed or censored ratio carries no numbers.** Whenever ``status`` is not ``OK`` or
    ``censoring`` is not ``NONE``, ``shape``, ``estimate``, ``lo`` and ``hi`` are all ``None`` --
    censoring propagation (what a censored input threshold does to the ratio) is Phase 6 work
    and is deliberately left undefined rather than guessed at here. Only on the ``OK`` +
    ``NONE`` path is ``shape`` required to be set, along with the numbers it governs.

    Attributes
    ----------
    threshold_a, threshold_b
        The two :class:`~marginkit.Threshold` results the ratio is between (``a / b``). Their
        axes must match on ``name`` and ``unit`` (R5), and their ``definition`` must be equal
        (a ratio between two different target-performance definitions is not one number); a
        mismatch on either raises. With ``dependence="independent"``, the two fits must not
        share a cluster id (§5.6). This object-level check is **necessary, not sufficient**:
        it can only see the ``cluster_ids`` a :class:`~marginkit.Fit` records, not whether the
        two series were drawn from overlapping observations that carry no cluster id. Equal
        fits are not rejected: two disjoint samples can produce identical counts, and that
        ratio is valid. The full
        shared-data check, including observation ids, belongs to ``ratio_interval`` (§5.6),
        which is Phase 6 work and not part of this release.
    estimate
        The point estimate of the ratio. Required and equal to
        ``threshold_a.value / threshold_b.value`` (``math.isclose``, ``rel_tol=1e-9``) when
        ``status`` is ``OK`` and ``censoring`` is ``NONE``; ``None`` otherwise.
    lo, hi
        The interval endpoints, read according to ``shape``, only when ``status`` is ``OK`` and
        ``censoring`` is ``NONE``:

        - ``BOUNDED``: ``[lo, hi]``, both set, ``lo <= hi``, and ``lo <= estimate <= hi``.
          ``method="log_delta"`` additionally requires ``lo > 0``.
        - ``UNBOUNDED``: both ``None`` (the whole real line); it carries ``estimate``.
        - ``EXCLUSIVE``: both set, ``lo < hi`` strictly, meaning
          ``(-inf, lo] union [hi, inf)``, and ``estimate`` lies in that union (``estimate <=
          lo`` or ``estimate >= hi``) -- the point estimate always lies inside the Fieller
          confidence set, never in the excluded gap.

        Both ``None`` otherwise.
    shape
        The :class:`~marginkit.IntervalShape` of ``(lo, hi)`` when ``status`` is ``OK`` and
        ``censoring`` is ``NONE``; ``None`` otherwise (including when ``status``/``censoring``
        make a shape meaningless).
    method
        ``"fieller"`` or ``"log_delta"``. ``"log_delta"`` additionally requires, on the
        ``OK`` + ``NONE`` path, that ``threshold_a.axis.scale`` and ``threshold_b.axis.scale``
        are both ``"log"`` and that ``threshold_a.value`` and ``threshold_b.value`` are both
        ``> 0`` (the log-scale delta method is undefined off the log axis or through zero).
    dependence
        ``"independent"`` in v0.1 (v0.2 adds ``"paired"``, §5.6). With ``"independent"``, the
        two thresholds' fits must not share a cluster id.
    level
        The confidence level, strictly between 0 and 1.
    censoring
        The :class:`~marginkit.Censoring` propagated from the input thresholds. Its meaning
        beyond ``NONE`` is Phase 6 work.
    status
        The :class:`~marginkit.Status` of this ratio.
    warnings
        Free-text notes surfaced alongside the ratio. Empty by default.
    schema_version
        The serialised-result schema version this object belongs to. Defaults to ``"1"``.
    provenance
        An opaque mapping the caller may attach to record where the inputs came from.
        marginkit stores it and never interprets it. Empty by default.
    """

    threshold_a: Threshold
    threshold_b: Threshold
    estimate: float | None
    lo: float | None
    hi: float | None
    shape: IntervalShape | None
    method: str
    dependence: str
    level: float
    censoring: Censoring
    status: Status
    warnings: tuple[str, ...] = ()
    schema_version: str = "1"
    provenance: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))

        if self.threshold_a.axis.name != self.threshold_b.axis.name:
            raise ValueError(
                "Ratio.threshold_a and .threshold_b must share an axis name, got "
                f"{self.threshold_a.axis.name!r} and {self.threshold_b.axis.name!r}"
            )
        if self.threshold_a.axis.unit != self.threshold_b.axis.unit:
            raise ValueError(
                "Ratio.threshold_a and .threshold_b must share an axis unit, got "
                f"{self.threshold_a.axis.unit!r} and {self.threshold_b.axis.unit!r}"
            )
        if self.threshold_a.definition != self.threshold_b.definition:
            raise ValueError(
                "Ratio.threshold_a.definition must equal Ratio.threshold_b.definition, got "
                f"{self.threshold_a.definition!r} and {self.threshold_b.definition!r}"
            )

        if self.method not in _VALID_METHODS:
            raise ValueError(
                f"Ratio.method must be one of {sorted(_VALID_METHODS)}, got {self.method!r}"
            )
        if self.dependence not in _VALID_DEPENDENCE:
            raise ValueError(
                f"Ratio.dependence must be one of {sorted(_VALID_DEPENDENCE)}, "
                f"got {self.dependence!r}"
            )
        _check_finite_number(self.level, label="Ratio.level")
        if not (0.0 < self.level < 1.0):
            raise ValueError(f"Ratio.level must satisfy 0 < level < 1, got {self.level!r}")

        if self.dependence == "independent":
            ids_a = self.threshold_a.fit.cluster_ids
            ids_b = self.threshold_b.fit.cluster_ids
            if ids_a is not None and ids_b is not None:
                overlap = set(ids_a) & set(ids_b)
                if overlap:
                    raise ValueError(
                        "Ratio: threshold_a.fit and threshold_b.fit share cluster id(s) "
                        f"{sorted(overlap, key=str)!r}, which is incompatible with "
                        "dependence='independent' (section 5.6)"
                    )

        _check_finite(self.estimate, label="estimate")
        _check_finite(self.lo, label="lo")
        _check_finite(self.hi, label="hi")

        is_ok_none = self.status is Status.OK and self.censoring is Censoring.NONE

        if not is_ok_none:
            if (
                self.shape is not None
                or self.estimate is not None
                or self.lo is not None
                or self.hi is not None
            ):
                raise ValueError(
                    "Ratio.shape, .estimate, .lo and .hi must all be None when status is not "
                    "OK or censoring is not NONE"
                )
            return

        if self.shape is None:
            raise ValueError("Ratio.shape must be set when status is OK and censoring is NONE")

        if self.threshold_a.censoring is not Censoring.NONE:
            raise ValueError(
                "Ratio.threshold_a.censoring must be NONE when the ratio's own status is OK "
                f"and censoring is NONE, got {self.threshold_a.censoring!r}"
            )
        if self.threshold_b.censoring is not Censoring.NONE:
            raise ValueError(
                "Ratio.threshold_b.censoring must be NONE when the ratio's own status is OK "
                f"and censoring is NONE, got {self.threshold_b.censoring!r}"
            )

        if self.threshold_a.status is not Status.OK or self.threshold_a.value is None:
            raise ValueError(
                "Ratio.threshold_a must have status OK with value set when the ratio's own "
                "status is OK and censoring is NONE"
            )
        if self.threshold_b.status is not Status.OK or self.threshold_b.value is None:
            raise ValueError(
                "Ratio.threshold_b must have status OK with value set when the ratio's own "
                "status is OK and censoring is NONE"
            )

        if self.estimate is None:
            raise ValueError("Ratio.estimate must be set when status is OK and censoring is NONE")
        estimate = self.estimate

        if not self.threshold_b.value > 0.0:
            raise ValueError(
                "Ratio.threshold_b.value must be > 0 to divide by (section 5.3), got "
                f"{self.threshold_b.value!r}"
            )
        expected = self.threshold_a.value / self.threshold_b.value
        if not math.isclose(estimate, expected, rel_tol=1e-9):
            raise ValueError(
                "Ratio.estimate must equal threshold_a.value / threshold_b.value "
                f"({expected!r}), got {estimate!r}"
            )

        if self.shape is IntervalShape.BOUNDED:
            if self.lo is None or self.hi is None:
                raise ValueError(
                    "Ratio.lo and .hi must both be set when shape is BOUNDED and censoring is NONE"
                )
            if not self.lo <= self.hi:
                raise ValueError(
                    f"Ratio.lo must not exceed .hi when shape is BOUNDED, got lo={self.lo!r}, "
                    f"hi={self.hi!r}"
                )
            if not (self.lo <= estimate <= self.hi):
                raise ValueError(
                    "Ratio.estimate must lie within [lo, hi] when shape is BOUNDED, got "
                    f"estimate={estimate!r}, lo={self.lo!r}, hi={self.hi!r}"
                )
            if self.method == "log_delta" and not self.lo > 0.0:
                raise ValueError(
                    f"Ratio.lo must be > 0 when method='log_delta', got lo={self.lo!r}"
                )
        elif self.shape is IntervalShape.UNBOUNDED:
            if self.lo is not None or self.hi is not None:
                raise ValueError(
                    "Ratio.lo and .hi must both be None when shape is UNBOUNDED and censoring "
                    "is NONE"
                )
        elif self.shape is IntervalShape.EXCLUSIVE:
            if self.lo is None or self.hi is None:
                raise ValueError(
                    "Ratio.lo and .hi must both be set when shape is EXCLUSIVE and censoring "
                    "is NONE"
                )
            if not self.lo < self.hi:
                raise ValueError(
                    "Ratio.lo must be strictly less than .hi when shape is EXCLUSIVE, got "
                    f"lo={self.lo!r}, hi={self.hi!r}"
                )
            if not (estimate <= self.lo or estimate >= self.hi):
                raise ValueError(
                    "Ratio.estimate must lie outside (lo, hi) when shape is EXCLUSIVE, got "
                    f"estimate={estimate!r}, lo={self.lo!r}, hi={self.hi!r}"
                )

        if self.method == "log_delta":
            if self.threshold_a.axis.scale != "log" or self.threshold_b.axis.scale != "log":
                raise ValueError(
                    "Ratio.method='log_delta' requires threshold_a.axis.scale and "
                    "threshold_b.axis.scale to both be 'log', got "
                    f"{self.threshold_a.axis.scale!r} and {self.threshold_b.axis.scale!r}"
                )
            if not (self.threshold_a.value > 0.0 and self.threshold_b.value > 0.0):
                raise ValueError(
                    "Ratio.method='log_delta' requires threshold_a.value and "
                    f"threshold_b.value to both be > 0, got {self.threshold_a.value!r} and "
                    f"{self.threshold_b.value!r}"
                )
            if self.shape is not IntervalShape.BOUNDED:
                raise ValueError(
                    f"Ratio.method='log_delta' requires shape=BOUNDED, got shape={self.shape!r}"
                )
