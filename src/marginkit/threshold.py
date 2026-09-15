"""The threshold result and its censoring/status invariants (§5.5).

As of ``0.1.0a2`` this module holds only :class:`Threshold`. Solving for a threshold
(``threshold()``, plan §4, §5.3-§5.5) is Phase 5 work and is not part of this release: there is
no way to produce a non-fake :class:`Threshold` yet, only to construct one directly or via
:func:`marginkit.testing.fake_threshold`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from marginkit.models import Fit
from marginkit.types import Axis, Censoring, Definition, JSONValue, Status, _check_finite_number

__all__ = ["Threshold"]

_VALID_INTERVAL_METHODS = frozenset({"profile", "delta", "exact_bound"})
_TERMINAL_STATUSES = frozenset(
    {Status.UNREACHABLE, Status.CONTROL_INCOMPATIBLE, Status.FAILS_AT_BASELINE}
)
_NONCONVERGENT_STATUSES = frozenset({Status.SEPARATION, Status.NOT_CONVERGED})
_VALID_DIRECTIONS = frozenset({"decreasing", "increasing"})

# A threshold with a value, with status OK or UNREACHABLE, or with an open-sided censoring
# needs the fit underneath it to have actually converged.
_REQUIRE_FIT_OK_STATUSES = frozenset({Status.OK, Status.UNREACHABLE})
_REQUIRE_FIT_OK_CENSORING = frozenset({Censoring.OPEN_UPPER, Censoring.OPEN_LOWER})
# SEPARATION, NOT_CONVERGED and CONTROL_INCOMPATIBLE are properties of the fit itself; a
# threshold reporting one of these must be built on a fit reporting the very same status.
_MIRROR_FIT_STATUS_STATUSES = frozenset(
    {Status.SEPARATION, Status.NOT_CONVERGED, Status.CONTROL_INCOMPATIBLE}
)
_VALID_DEPENDENCE = frozenset({"independent"})


def _check_value(value: float | None, *, label: str, scale: str) -> None:
    if value is None:
        return
    _check_finite_number(value, label=f"Threshold.{label}")
    if scale == "log":
        if not value > 0.0:
            raise ValueError(f"Threshold.{label} must be > 0 on a log axis, got {value!r}")
    elif value < 0.0:
        raise ValueError(f"Threshold.{label} must be non-negative, got {value!r}")


@dataclass(frozen=True, kw_only=True)
class Threshold:
    """Where a fitted curve crosses a target performance, with a confidence interval, or an
    explicit record of why no value is reported (§5.5).

    Every censoring rule below assumes the **true** performance curve is monotone in severity
    (the fitted curve, being drawn from a monotone parametric family, is monotone by
    construction regardless). A ``RIGHT`` bound reads "threshold > lo (one-sided, exact,
    monotonicity assumed)", never as a value on its own; the mirrored reading applies to
    ``LEFT``. A ``SEPARATION``/``NOT_CONVERGED`` bracket is built from *two* one-sided exact
    bounds, each individually at confidence ``level``; their **joint** coverage is at least
    ``2 * level - 1`` (a Bonferroni-style bound), not ``level`` itself.

    Binomial curves are decreasing-only in this release: ``direction="increasing"`` raises,
    pending owner decision D5.

    Invariants enforced in ``__post_init__`` (§5.5's table, plus the fit-status and ordering
    rules the stats review added):

    - ``status`` in ``{UNREACHABLE, CONTROL_INCOMPATIBLE, FAILS_AT_BASELINE}``: ``value``,
      ``lo`` and ``hi`` are all ``None``; ``censoring`` is ``NONE``; ``interval_method`` is
      ``"exact_bound"``. There is no threshold at all in these cases -- either it cannot be
      reached given the fitted asymptotes, or the question of a crossing does not arise
      because the control already fails.
    - ``status`` in ``{SEPARATION, NOT_CONVERGED}``: ``value`` is ``None``; ``censoring`` is one
      of ``{NONE, RIGHT, LEFT}``; ``interval_method`` is ``"exact_bound"``; ``lo`` and ``hi``
      may be set, as the exact-bound fallback described in §5.2.
    - ``censoring == RIGHT``: ``value`` is ``None``, ``lo`` is set, ``hi`` is ``None``,
      ``interval_method == "exact_bound"``.
    - ``censoring == LEFT``: ``value`` is ``None``, ``hi`` is set, ``lo`` is ``None``,
      ``interval_method == "exact_bound"``.
    - ``censoring == OPEN_UPPER``: ``status == OK``, ``value`` and ``lo`` are set, ``hi`` is
      ``None``, ``interval_method == "profile"``. ``OPEN_LOWER`` mirrors it, with ``hi`` set
      and ``lo`` ``None``.
    - ``censoring == NONE`` with ``status == OK``: ``value``, ``lo`` and ``hi`` are all set,
      with ``lo <= value <= hi``, and ``interval_method`` is ``"profile"`` or ``"delta"``.
    - When both ``lo`` and ``hi`` are set: ``lo < hi`` strictly for a ``SEPARATION`` /
      ``NOT_CONVERGED`` bracket, ``lo <= hi`` otherwise.
    - On a log axis, ``value``, ``lo`` and ``hi`` must each be ``> 0`` when present (a linear
      axis keeps ``>= 0``).
    - ``fit.status`` must equal ``OK`` whenever ``value`` is set, ``status`` is ``OK`` or
      ``UNREACHABLE``, or ``censoring`` is ``OPEN_UPPER``/``OPEN_LOWER``. ``fit.status`` must
      equal ``status`` itself when ``status`` is ``SEPARATION``, ``NOT_CONVERGED`` or
      ``CONTROL_INCOMPATIBLE``. ``FAILS_AT_BASELINE`` places no constraint on ``fit.status``
      (the control's exact test does not depend on the rest of the curve having converged).

    Attributes
    ----------
    axis
        The :class:`~marginkit.Axis` this threshold was solved on. Must equal ``fit.axis``.
    definition
        Which target performance this threshold solves for (§5.3).
    direction
        ``"decreasing"`` only, in this release (see above). Carried over from ``fit``.
    value
        The estimated crossing severity, or ``None`` per the rules above.
    lo
        The interval's lower side, or a one-sided bound, or ``None``.
    hi
        The interval's upper side, or a one-sided bound, or ``None``.
    level
        The confidence level, strictly between 0 and 1.
    interval_method
        ``"profile"``, ``"delta"`` or ``"exact_bound"``.
    censoring
        The :class:`~marginkit.Censoring` classification.
    status
        The :class:`~marginkit.Status` of this threshold.
    dependence
        ``"independent"`` in this release. Required, with no default: a threshold built from
        clustered data must say so explicitly rather than silently assuming independence (R2).
    fit
        The :class:`~marginkit.Fit` this threshold was solved from. Per-level trial counts
        (R10) live on ``fit.cells``, not on a separate field.
    warnings
        Free-text notes surfaced alongside the threshold. Empty by default.
    schema_version
        The serialised-result schema version this object belongs to. Defaults to ``"1"``.
    provenance
        An opaque mapping the caller may attach to record where the inputs came from.
        marginkit stores it and never interprets it. Empty by default.
    """

    axis: Axis
    definition: Definition
    direction: str
    value: float | None
    lo: float | None
    hi: float | None
    level: float
    interval_method: str
    censoring: Censoring
    status: Status
    dependence: str
    fit: Fit
    warnings: tuple[str, ...] = ()
    schema_version: str = "1"
    provenance: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))

        if self.direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"Threshold.direction must be one of {sorted(_VALID_DIRECTIONS)}, "
                f"got {self.direction!r}"
            )
        if self.direction != "decreasing":
            raise ValueError(
                "Threshold: direction='increasing' is not supported in this release; an "
                "increasing-is-worse definition is pending owner decision D5"
            )
        if self.interval_method not in _VALID_INTERVAL_METHODS:
            raise ValueError(
                f"Threshold.interval_method must be one of {sorted(_VALID_INTERVAL_METHODS)}, "
                f"got {self.interval_method!r}"
            )
        if self.dependence not in _VALID_DEPENDENCE:
            raise ValueError(
                f"Threshold.dependence must be one of {sorted(_VALID_DEPENDENCE)}, "
                f"got {self.dependence!r}"
            )
        _check_finite_number(self.level, label="Threshold.level")
        if not (0.0 < self.level < 1.0):
            raise ValueError(f"Threshold.level must satisfy 0 < level < 1, got {self.level!r}")
        if self.axis != self.fit.axis:
            raise ValueError("Threshold.axis must equal Threshold.fit.axis")
        if self.direction != self.fit.direction:
            raise ValueError("Threshold.direction must equal Threshold.fit.direction")

        _check_value(self.value, label="value", scale=self.axis.scale)
        _check_value(self.lo, label="lo", scale=self.axis.scale)
        _check_value(self.hi, label="hi", scale=self.axis.scale)

        requires_fit_ok = (
            self.value is not None
            or self.status in _REQUIRE_FIT_OK_STATUSES
            or self.censoring in _REQUIRE_FIT_OK_CENSORING
        )
        if requires_fit_ok and self.fit.status is not Status.OK:
            raise ValueError(
                "Threshold.fit.status must be OK when value is set, status is OK or "
                "UNREACHABLE, or censoring is OPEN_UPPER/OPEN_LOWER; got "
                f"fit.status={self.fit.status!r}"
            )
        if self.status in _MIRROR_FIT_STATUS_STATUSES and self.fit.status is not self.status:
            raise ValueError(
                f"Threshold.fit.status must equal Threshold.status ({self.status!r}) when "
                "status is SEPARATION, NOT_CONVERGED or CONTROL_INCOMPATIBLE; got "
                f"fit.status={self.fit.status!r}"
            )

        if self.lo is not None and self.hi is not None:
            if self.status in _NONCONVERGENT_STATUSES:
                if not self.lo < self.hi:
                    raise ValueError(
                        "Threshold.lo must be strictly less than .hi for a "
                        f"SEPARATION/NOT_CONVERGED bracket, got lo={self.lo!r}, hi={self.hi!r}"
                    )
            elif not self.lo <= self.hi:
                raise ValueError(
                    f"Threshold.lo must not exceed .hi, got lo={self.lo!r}, hi={self.hi!r}"
                )

        if self.status in _TERMINAL_STATUSES:
            if self.value is not None or self.lo is not None or self.hi is not None:
                raise ValueError(
                    f"Threshold.value, .lo and .hi must all be None when status={self.status!r}"
                )
            if self.censoring is not Censoring.NONE:
                raise ValueError(
                    f"Threshold.censoring must be NONE when status={self.status!r}, "
                    f"got {self.censoring!r}"
                )
            if self.interval_method != "exact_bound":
                raise ValueError(
                    "Threshold.interval_method must be 'exact_bound' when "
                    f"status={self.status!r}, got {self.interval_method!r}"
                )
            return

        if self.status in _NONCONVERGENT_STATUSES:
            if self.interval_method != "exact_bound":
                raise ValueError(
                    f"Threshold.interval_method must be 'exact_bound' when "
                    f"status={self.status!r}, got {self.interval_method!r}"
                )
            if self.value is not None:
                raise ValueError(f"Threshold.value must be None when status={self.status!r}")
            if self.censoring not in (Censoring.NONE, Censoring.RIGHT, Censoring.LEFT):
                raise ValueError(
                    f"Threshold.censoring must be one of NONE, RIGHT, LEFT when "
                    f"status={self.status!r}, got {self.censoring!r}"
                )

        if self.censoring is Censoring.RIGHT:
            if self.interval_method != "exact_bound":
                raise ValueError(
                    "Threshold.interval_method must be 'exact_bound' when censoring is RIGHT, "
                    f"got {self.interval_method!r}"
                )
            if self.value is not None:
                raise ValueError("Threshold.value must be None when censoring is RIGHT")
            if self.lo is None:
                raise ValueError("Threshold.lo must be set when censoring is RIGHT")
            if self.hi is not None:
                raise ValueError("Threshold.hi must be None when censoring is RIGHT")
        elif self.censoring is Censoring.LEFT:
            if self.interval_method != "exact_bound":
                raise ValueError(
                    "Threshold.interval_method must be 'exact_bound' when censoring is LEFT, "
                    f"got {self.interval_method!r}"
                )
            if self.value is not None:
                raise ValueError("Threshold.value must be None when censoring is LEFT")
            if self.hi is None:
                raise ValueError("Threshold.hi must be set when censoring is LEFT")
            if self.lo is not None:
                raise ValueError("Threshold.lo must be None when censoring is LEFT")
        elif self.censoring is Censoring.OPEN_UPPER:
            if self.status is not Status.OK:
                raise ValueError("Threshold.censoring OPEN_UPPER requires status OK")
            if self.interval_method != "profile":
                raise ValueError(
                    "Threshold.interval_method must be 'profile' when censoring is OPEN_UPPER, "
                    f"got {self.interval_method!r}"
                )
            if self.value is None or self.lo is None:
                raise ValueError("Threshold.value and .lo must be set when censoring is OPEN_UPPER")
            if self.hi is not None:
                raise ValueError("Threshold.hi must be None when censoring is OPEN_UPPER")
        elif self.censoring is Censoring.OPEN_LOWER:
            if self.status is not Status.OK:
                raise ValueError("Threshold.censoring OPEN_LOWER requires status OK")
            if self.interval_method != "profile":
                raise ValueError(
                    "Threshold.interval_method must be 'profile' when censoring is OPEN_LOWER, "
                    f"got {self.interval_method!r}"
                )
            if self.value is None or self.hi is None:
                raise ValueError("Threshold.value and .hi must be set when censoring is OPEN_LOWER")
            if self.lo is not None:
                raise ValueError("Threshold.lo must be None when censoring is OPEN_LOWER")
        elif self.censoring is Censoring.NONE and self.status is Status.OK:
            if self.value is None or self.lo is None or self.hi is None:
                raise ValueError(
                    "Threshold.value, .lo and .hi must all be set when censoring is NONE and "
                    "status is OK"
                )
            if not (self.lo <= self.value <= self.hi):
                raise ValueError(
                    f"Threshold requires lo <= value <= hi, got lo={self.lo!r}, "
                    f"value={self.value!r}, hi={self.hi!r}"
                )
            if self.interval_method not in ("profile", "delta"):
                raise ValueError(
                    "Threshold.interval_method must be 'profile' or 'delta' when censoring is "
                    f"NONE and status is OK, got {self.interval_method!r}"
                )
