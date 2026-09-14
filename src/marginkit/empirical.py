"""The grid break-point rule, copied into marginkit under neutral names.

``grid_break_point`` reproduces the semantics of zeta-bench's
``robustness/cards.py::break_point`` (commit ``435fc2793b2afdb8404099c83b0c36a71d9ffba9``,
PR #17): the smallest tested severity magnitude at which performance falls strictly below a
criterion, or an explicit right-censored result when no tested level fails. See
``docs/PROVENANCE.md`` for which conventions were carried over, what was deliberately changed
(empty input, non-finite values, and unsigned negative severities now raise rather than
returning a silent fallback), and why.

This module holds only the grid rule. Model-based dose-response estimation is new work, not a
port, and is not part of this release.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike

from marginkit.types import Censoring

__all__ = ["GridBreakPoint", "grid_break_point"]


@dataclass(frozen=True)
class GridBreakPoint:
    """The result of :func:`grid_break_point`: an observed grid statistic, not a threshold.

    Attributes
    ----------
    value
        The smallest *tested* severity magnitude whose performance was strictly below the
        criterion, or ``None`` if no tested level failed. It is always one of the tested
        magnitudes, never a fitted or interpolated estimate of where performance crosses the
        criterion, and it carries no confidence interval.

        Read as a location for the crossing, it is only an **upper bound at grid resolution**.
        If performance were monotone, the crossing would lie somewhere in the half-open gap
        between the largest passing tested magnitude below ``value`` and ``value`` itself. When
        ``value`` equals the smallest tested magnitude (including ``0.0``), no passing level
        was observed below it at all. Monotonicity is neither assumed nor checked.
    max_tested
        The largest tested severity magnitude. Always reported, so a right-censored result can
        be read as "held up to ``max_tested``" rather than as an unqualified pass.
    censoring
        A **point-estimate label for the grid**, not the censoring classification a model-based
        threshold reports. :data:`~marginkit.types.Censoring.RIGHT` means no tested level's
        performance fell below the criterion (``value is None``).
        :data:`~marginkit.types.Censoring.NONE` means at least one did. No exact one-sided test
        is applied and no monotonicity is assumed, so ``RIGHT`` here is weaker than a
        statistical lower bound. ``NONE`` does not mean the criterion was bracketed: a zero
        level that already fails gives ``value == 0.0`` with ``NONE``. The grid rule never
        produces ``LEFT``, ``OPEN_UPPER``, or ``OPEN_LOWER``.
    schema_version
        The version of the serialised result schema this object belongs to. Defaults to
        ``"1"``.
    provenance
        An opaque mapping the caller may attach (for example with :func:`dataclasses.replace`)
        to record where the inputs came from. marginkit stores it and never interprets it.
        Empty by default.
    """

    value: float | None
    max_tested: float
    censoring: Censoring
    schema_version: str = "1"
    provenance: Mapping[str, object] = field(default_factory=dict)


def grid_break_point(
    severity: ArrayLike,
    performance: ArrayLike,
    *,
    criterion: float,
    signed: bool = False,
) -> GridBreakPoint:
    """Find the smallest tested severity magnitude whose performance fails a criterion.

    A level fails when its performance is strictly below ``criterion``. A level sitting exactly
    on the criterion passes. This is a statistic over the levels actually tested, not a fitted
    or interpolated estimate: the reported ``value`` is always one of the tested magnitudes, or
    ``None`` when the criterion held everywhere. A ``None`` value paired with
    :data:`~marginkit.types.Censoring.RIGHT` means performance held up to ``max_tested``. It
    does not mean the system cannot be broken, only that breaking it was not observed within
    the range that was tested.

    Parameters
    ----------
    severity
        One-dimensional severity levels tested. Must be non-negative unless ``signed=True``.
    performance
        One-dimensional performance values, one per ``severity`` entry, on whatever scale the
        caller has already put them on (for example, a success rate).
    criterion
        The performance level a passing observation must reach or exceed. The comparison is
        strict: ``performance < criterion`` is a failure, ``performance == criterion`` is a
        pass.
    signed
        If ``False`` (the default), a negative ``severity`` entry is treated as caller error and
        raises. If ``True``, ``severity`` may be signed and the rule breaks on magnitude: the
        side that fails at the smallest ``abs(severity)`` determines ``value``.

    Returns
    -------
    GridBreakPoint
        ``value`` is the smallest tested failing magnitude, or ``None``. ``max_tested`` is the
        largest tested magnitude. ``censoring`` is the grid label described on
        :class:`GridBreakPoint`.

    Raises
    ------
    ValueError
        If ``severity`` or ``performance`` is empty, is not one-dimensional, or the two have
        mismatched lengths. Also if any value in ``severity``, ``performance``, or
        ``criterion`` is non-finite, or if ``severity`` contains a negative value while
        ``signed=False``.

    Notes
    -----
    The caller decides what "severity" and "performance" mean on a given axis, for example
    which nuisance factors were pooled to produce ``performance``. This rule performs no
    pooling and fits no model, and it neither assumes nor checks that performance is monotone
    in severity.

    All inputs are converted to float64 before comparing, so the comparison is exact in
    float64. A float32 performance of ``0.95`` is ``0.949999988...`` and therefore fails a
    criterion of ``0.95``.
    """
    severity_arr = np.asarray(severity, dtype=np.float64)
    performance_arr = np.asarray(performance, dtype=np.float64)

    if severity_arr.ndim != 1:
        raise ValueError(f"severity must be 1-D, got shape {severity_arr.shape}")
    if performance_arr.ndim != 1:
        raise ValueError(f"performance must be 1-D, got shape {performance_arr.shape}")
    if severity_arr.size == 0:
        raise ValueError("severity and performance must not be empty")
    if severity_arr.size != performance_arr.size:
        raise ValueError(
            "severity and performance must have the same length, got "
            f"{severity_arr.size} and {performance_arr.size}"
        )
    if not np.all(np.isfinite(severity_arr)):
        raise ValueError("severity must be finite (no NaN or inf)")
    if not np.all(np.isfinite(performance_arr)):
        raise ValueError("performance must be finite (no NaN or inf)")
    if not math.isfinite(criterion):
        raise ValueError("criterion must be finite (no NaN or inf)")
    if not signed and bool(np.any(severity_arr < 0.0)):
        raise ValueError("severity must be non-negative unless signed=True")

    magnitude = np.abs(severity_arr)
    max_tested = float(np.max(magnitude))

    failing = magnitude[performance_arr < criterion]
    if failing.size == 0:
        return GridBreakPoint(value=None, max_tested=max_tested, censoring=Censoring.RIGHT)

    return GridBreakPoint(
        value=float(np.min(failing)), max_tested=max_tested, censoring=Censoring.NONE
    )
