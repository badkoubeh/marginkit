"""Schema-valid fake results for **consumers' own tests** (plan section 3.3's "unblock
marginbench early").

``fake_fit``, ``fake_threshold`` and ``fake_ratio`` build deterministic, schema-valid
:class:`~marginkit.Fit`, :class:`~marginkit.Threshold` and :class:`~marginkit.Ratio` objects so
a consumer can write and run its own report-rendering tests before marginkit's real statistics
(Phases 4-6) exist. They are **not** statistical estimates of anything: every one of them
carries a warning saying so, and nothing here should be read as a claim about what a real fit
would produce for the same inputs.
"""

from __future__ import annotations

from collections.abc import Mapping

from marginkit.models import Covariance, Fit, Parameter
from marginkit.ratio import Ratio
from marginkit.threshold import Threshold
from marginkit.types import Axis, Cell, Censoring, Definition, IntervalShape, JSONValue, Status

__all__ = ["fake_fit", "fake_ratio", "fake_threshold"]

_AXIS = Axis(name="severity", unit="unit", scale="log")
_FAKE_WARNING = (
    "This is a fake object from marginkit.testing, built for a consumer's own tests. It is "
    "schema-valid, not a statistical estimate."
)
_CELLS: tuple[Cell, ...] = (
    Cell(severity=0.0, successes=100, trials=100),
    Cell(severity=1.0, successes=60, trials=100),
    Cell(severity=2.0, successes=20, trials=100),
)
# fake_ratio builds its two thresholds from two separate fits on disjoint data (different
# severities entirely), not the same _CELLS reused twice, so a consumer's test never mistakes
# the pair for a ratio computed from one dataset against itself.
_CELLS_A: tuple[Cell, ...] = _CELLS
_CELLS_B: tuple[Cell, ...] = (
    # severity=0.0 is an all-success control, like _CELLS_A's: 'upper' is fixed at exactly 1.0
    # in _fake_ok_params_and_covariance, and a failing control combined with a fixed upper=1.0
    # makes the likelihood zero on a log axis (Fit's own check, section 5.1).
    Cell(severity=0.0, successes=100, trials=100),
    Cell(severity=1.5, successes=50, trials=100),
    Cell(severity=3.0, successes=10, trials=100),
)

# The 14 (status, censoring) combinations plan section 5.5 allows for a Threshold (the Phase 3
# plan's worked breakdown), mirroring the invariants Threshold.__post_init__ enforces.
_ALLOWED_THRESHOLD_COMBINATIONS: frozenset[tuple[Status, Censoring]] = frozenset(
    {(Status.OK, censoring) for censoring in Censoring}
    | {
        (status, censoring)
        for status in (Status.SEPARATION, Status.NOT_CONVERGED)
        for censoring in (Censoring.NONE, Censoring.RIGHT, Censoring.LEFT)
    }
    | {
        (status, Censoring.NONE)
        for status in (Status.UNREACHABLE, Status.FAILS_AT_BASELINE, Status.CONTROL_INCOMPATIBLE)
    }
)

# UNREACHABLE and FAILS_AT_BASELINE are properties of a perfectly good fit (the target
# performance is out of the fitted curve's range, or the control already fails); SEPARATION,
# NOT_CONVERGED and CONTROL_INCOMPATIBLE are properties of the fit itself, so a threshold with
# one of those statuses is built on a fit carrying the same status (section 5.5 stats review).
_FIT_STATUS_FOR_THRESHOLD_STATUS: dict[Status, Status] = {
    Status.OK: Status.OK,
    Status.UNREACHABLE: Status.OK,
    Status.FAILS_AT_BASELINE: Status.OK,
    Status.SEPARATION: Status.SEPARATION,
    Status.NOT_CONVERGED: Status.NOT_CONVERGED,
    Status.CONTROL_INCOMPATIBLE: Status.CONTROL_INCOMPATIBLE,
}


def _fake_provenance(provenance: Mapping[str, JSONValue] | None) -> dict[str, JSONValue]:
    return dict(provenance) if provenance is not None else {}


def _fake_ok_params_and_covariance() -> tuple[dict[str, Parameter], Covariance]:
    params = {
        "mu": Parameter(value=0.5, fixed=False),
        "s": Parameter(value=0.3, fixed=False),
        "upper": Parameter(value=1.0, fixed=True),
        "lower": Parameter(value=0.0, fixed=True),
    }
    covariance = Covariance(names=("mu", "s"), matrix=((0.01, 0.0), (0.0, 0.02)))
    return params, covariance


def _fake_ok_fit(
    cells: tuple[Cell, ...], *, provenance: Mapping[str, JSONValue] | None = None
) -> Fit:
    params, covariance = _fake_ok_params_and_covariance()
    return Fit(
        axis=_AXIS,
        outcome="success",
        direction="decreasing",
        model="binomial",
        link="probit",
        params=params,
        covariance=covariance,
        log_likelihood=-12.5,
        cells=cells,
        status=Status.OK,
        cluster_ids=None,
        warnings=(_FAKE_WARNING,),
        provenance=_fake_provenance(provenance),
    )


def fake_fit(
    *, status: Status = Status.OK, provenance: Mapping[str, JSONValue] | None = None
) -> Fit:
    """Build a deterministic, schema-valid :class:`~marginkit.Fit`.

    Parameters
    ----------
    status
        The :class:`~marginkit.Status` to build. Every member other than ``UNREACHABLE`` and
        ``FAILS_AT_BASELINE`` is accepted (those describe a threshold, not a fit, and
        :class:`~marginkit.Fit` itself rejects them). When ``status`` is not ``OK``, ``params``,
        ``covariance`` and ``log_likelihood`` are all ``None``, matching
        :class:`~marginkit.Fit`'s own invariant.
    provenance
        Stored on the result as given, or ``{}`` if not provided.

    Returns
    -------
    Fit
        A binomial-probit fit on a neutral ``severity`` axis, with ``cluster_ids=None`` and
        ``warnings`` naming it a fake.
    """
    if status is Status.OK:
        return _fake_ok_fit(_CELLS, provenance=provenance)

    return Fit(
        axis=_AXIS,
        outcome="success",
        direction="decreasing",
        model="binomial",
        link="probit",
        params=None,
        covariance=None,
        log_likelihood=None,
        cells=_CELLS,
        status=status,
        cluster_ids=None,
        warnings=(_FAKE_WARNING,),
        provenance=_fake_provenance(provenance),
    )


def fake_threshold(
    *,
    status: Status = Status.OK,
    censoring: Censoring = Censoring.NONE,
    provenance: Mapping[str, JSONValue] | None = None,
) -> Threshold:
    """Build a deterministic, schema-valid :class:`~marginkit.Threshold`.

    Parameters
    ----------
    status
        The :class:`~marginkit.Status` to build.
    censoring
        The :class:`~marginkit.Censoring` to build.
    provenance
        Stored on the result as given, or ``{}`` if not provided.

    Returns
    -------
    Threshold
        A threshold on a neutral ``severity`` axis with ``dependence="independent"``, and
        ``warnings`` naming it a fake.

    Raises
    ------
    ValueError
        If ``(status, censoring)`` is not one of the fourteen combinations plan section 5.5
        allows for a ``Threshold``.
    """
    if (status, censoring) not in _ALLOWED_THRESHOLD_COMBINATIONS:
        raise ValueError(
            f"fake_threshold: status={status!r} with censoring={censoring!r} is not a "
            "combination plan section 5.5 allows for a Threshold"
        )

    fit = fake_fit(status=_FIT_STATUS_FOR_THRESHOLD_STATUS[status])

    value: float | None
    lo: float | None
    hi: float | None
    interval_method: str

    if status in (Status.UNREACHABLE, Status.FAILS_AT_BASELINE, Status.CONTROL_INCOMPATIBLE):
        value, lo, hi = None, None, None
        interval_method = "exact_bound"
    elif censoring is Censoring.RIGHT:
        value, lo, hi = None, 10.0, None
        interval_method = "exact_bound"
    elif censoring is Censoring.LEFT:
        value, lo, hi = None, None, 0.01
        interval_method = "exact_bound"
    elif censoring is Censoring.OPEN_UPPER:
        value, lo, hi = 0.05, 0.03, None
        interval_method = "profile"
    elif censoring is Censoring.OPEN_LOWER:
        value, lo, hi = 0.05, None, 0.08
        interval_method = "profile"
    elif status is Status.OK:
        value, lo, hi = 0.05, 0.03, 0.08
        interval_method = "profile"
    else:
        # SEPARATION / NOT_CONVERGED with censoring NONE (Sec. 5.2's exact-bound fallback,
        # with both sides happening to be available here).
        value, lo, hi = None, 0.02, 0.09
        interval_method = "exact_bound"

    return Threshold(
        axis=_AXIS,
        definition=Definition.absolute(0.95),
        direction="decreasing",
        value=value,
        lo=lo,
        hi=hi,
        level=0.95,
        interval_method=interval_method,
        censoring=censoring,
        status=status,
        dependence="independent",
        fit=fit,
        warnings=(_FAKE_WARNING,),
        provenance=_fake_provenance(provenance),
    )


def _fake_ok_threshold(*, fit: Fit, value: float, lo: float, hi: float) -> Threshold:
    return Threshold(
        axis=_AXIS,
        definition=Definition.absolute(0.95),
        direction="decreasing",
        value=value,
        lo=lo,
        hi=hi,
        level=0.95,
        interval_method="profile",
        censoring=Censoring.NONE,
        status=Status.OK,
        dependence="independent",
        fit=fit,
        warnings=(_FAKE_WARNING,),
        provenance={},
    )


def fake_ratio(
    *,
    shape: IntervalShape | None = None,
    status: Status = Status.OK,
    censoring: Censoring = Censoring.NONE,
    provenance: Mapping[str, JSONValue] | None = None,
) -> Ratio:
    """Build a deterministic, schema-valid :class:`~marginkit.Ratio`.

    A failed or censored ratio carries no numbers (owner decision): whenever ``status`` is not
    ``OK`` or ``censoring`` is not ``NONE``, ``shape``, ``estimate``, ``lo`` and ``hi`` are all
    ``None``, matching :class:`~marginkit.Ratio`'s own invariant.

    Parameters
    ----------
    shape
        The :class:`~marginkit.IntervalShape` to build. ``None`` (the default) means
        ``BOUNDED`` when ``status`` is ``OK`` and ``censoring`` is ``NONE``, and means "no
        shape" (forced ``None``) otherwise. Passing an explicit shape together with a non-``OK``
        ``status`` or a non-``NONE`` ``censoring`` raises ``ValueError``, since that combination
        can never be a valid ``Ratio``.
    status
        The :class:`~marginkit.Status` to build.
    censoring
        The :class:`~marginkit.Censoring` to build.
    provenance
        Stored on the result as given, or ``{}`` if not provided.

    Returns
    -------
    Ratio
        A ratio built from two fits on disjoint data (different cells entirely), with
        ``dependence="independent"``, ``cluster_ids=None`` on both fits, and ``warnings``
        naming it a fake. On the ``OK`` + ``NONE`` path, ``estimate`` is exactly
        ``threshold_a.value / threshold_b.value``, matching
        :class:`~marginkit.Ratio`'s own invariant; the point estimate always lies inside the
        Fieller confidence set described by ``shape``, including for ``EXCLUSIVE``.

    Raises
    ------
    ValueError
        If ``shape`` is given explicitly while ``status`` is not ``OK`` or ``censoring`` is not
        ``NONE``.
    """
    is_ok_none = status is Status.OK and censoring is Censoring.NONE
    if not is_ok_none and shape is not None:
        raise ValueError(
            f"fake_ratio: shape={shape!r} is not allowed when status={status!r} or "
            f"censoring={censoring!r} -- a failed or censored ratio carries no shape"
        )

    value_a, lo_a, hi_a = 0.05, 0.03, 0.08
    value_b, lo_b, hi_b = 0.1, 0.06, 0.16
    threshold_a = _fake_ok_threshold(fit=_fake_ok_fit(_CELLS_A), value=value_a, lo=lo_a, hi=hi_a)
    threshold_b = _fake_ok_threshold(fit=_fake_ok_fit(_CELLS_B), value=value_b, lo=lo_b, hi=hi_b)

    resolved_shape: IntervalShape | None
    estimate: float | None
    lo: float | None
    hi: float | None

    if not is_ok_none:
        resolved_shape, estimate, lo, hi = None, None, None, None
    else:
        resolved_shape = IntervalShape.BOUNDED if shape is None else shape
        ratio_value = value_a / value_b
        estimate = ratio_value
        if resolved_shape is IntervalShape.BOUNDED:
            lo, hi = 0.3, 0.7
        elif resolved_shape is IntervalShape.UNBOUNDED:
            lo, hi = None, None
        else:
            # EXCLUSIVE: the point estimate sits on the near edge of the excluded gap, inside
            # the (-inf, lo] ray of the Fieller confidence set.
            lo, hi = ratio_value, ratio_value + 1.0

    return Ratio(
        threshold_a=threshold_a,
        threshold_b=threshold_b,
        estimate=estimate,
        lo=lo,
        hi=hi,
        shape=resolved_shape,
        method="fieller",
        dependence="independent",
        level=0.95,
        censoring=censoring,
        status=status,
        warnings=(_FAKE_WARNING,),
        provenance=_fake_provenance(provenance),
    )
