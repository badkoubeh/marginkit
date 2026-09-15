"""The dose-response fit result and its parameter/covariance helpers.

As of ``0.1.0a2`` this module holds only :class:`Fit` and the two small dataclasses it embeds,
:class:`Parameter` and :class:`Covariance`. Fitting itself (``fit_dose_response``, plan §4,
§5.1) is Phase 4 work and is not part of this release: there is no way to produce a
non-fake :class:`Fit` yet, only to construct one directly or via :func:`marginkit.testing.fake_fit`.

**v1 is binomial-only.** ``model`` accepts only ``"binomial"``; a new model family (``"ll4"``,
``"isotonic"``) is a v0.2 addition that requires ``schema_version`` ``"2"``, not a silent
extension of this one.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from marginkit.types import Axis, Cell, JSONValue, Status, _check_finite_number

__all__ = ["Covariance", "Fit", "Parameter"]

_VALID_MODELS = frozenset({"binomial"})
_VALID_LINKS: dict[str, frozenset[str]] = {
    "binomial": frozenset({"probit", "logit", "cloglog"}),
}
_BINOMIAL_PARAM_NAMES = frozenset({"mu", "s", "upper", "lower"})
_VALID_DIRECTIONS = frozenset({"decreasing", "increasing"})
_INVALID_FIT_STATUSES = frozenset({Status.UNREACHABLE, Status.FAILS_AT_BASELINE})

# Tolerance for Covariance's positive-definiteness check: the minimum eigenvalue must exceed
# this, scaled by the matrix's largest magnitude entry so the tolerance is not swamped by the
# matrix's own scale. Strictly positive (not the semi-definite ``>= -tolerance`` this used to
# be): a singular matrix, such as ``((0.0, 0.0), (0.0, 1.0))``, is rejected, because a singular
# covariance means at least one estimated parameter carries no information at all.
_POSITIVE_DEFINITE_RELATIVE_TOLERANCE = 1e-12


@dataclass(frozen=True, kw_only=True)
class Parameter:
    """One fitted or fixed parameter value, on the **natural scale** -- the curve's own units
    (for example ``s`` in log-severity units, ``upper``/``lower`` as probabilities), never the
    optimiser's internal reparametrisation (``log s``, or ``upper``/``lower`` on a logit scale).
    An estimated-asymptote fit delta-transforms its optimiser-scale covariance onto this scale
    before it is ever stored here (see :class:`Fit`).

    Attributes
    ----------
    value
        The parameter's value on its natural scale. Must be finite, and must be a genuine
        ``float`` or ``int``, never a ``bool``.
    fixed
        ``True`` if this parameter was held fixed rather than estimated (for example
        ``upper=1.0`` fixed in a two-parameter probit). Must be a genuine ``bool``.
    """

    value: float
    fixed: bool

    def __post_init__(self) -> None:
        _check_finite_number(self.value, label="Parameter.value")
        if not isinstance(self.fixed, bool):
            raise ValueError(f"Parameter.fixed must be a real bool, got {self.fixed!r}")


@dataclass(frozen=True, kw_only=True)
class Covariance:
    """The variance-covariance matrix of a fit's estimated (non-fixed) parameters, on the same
    natural scale as :class:`Parameter`.

    Attributes
    ----------
    names
        The estimated parameter names, in the order ``matrix`` is indexed by. Unique.
    matrix
        A square, finite, symmetric, **positive-definite** matrix with side ``len(names)``.
        Every entry must be a genuine finite number, never a ``bool``. Symmetry is checked with
        :func:`math.isclose` (``rel_tol=1e-9``, ``abs_tol=1e-12``), not exact equality, to
        tolerate floating-point round-trip noise. Positive-definiteness is checked via
        :func:`numpy.linalg.eigvalsh`: the minimum eigenvalue must exceed
        ``1e-12 * max(1, max(abs(entry)))``, the same relative tolerance for the same reason. A
        singular matrix -- for example ``((0.0, 0.0), (0.0, 1.0))``, or any matrix with a zero
        eigenvalue -- is rejected, not merely a matrix with a negative one.
    """

    names: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "names", tuple(self.names))
        object.__setattr__(self, "matrix", tuple(tuple(row) for row in self.matrix))

        if len(set(self.names)) != len(self.names):
            raise ValueError(f"Covariance.names must be unique, got {self.names!r}")

        n = len(self.names)
        if len(self.matrix) != n:
            raise ValueError(
                f"Covariance.matrix must have {n} rows to match names, got {len(self.matrix)}"
            )
        for row in self.matrix:
            if len(row) != n:
                raise ValueError(
                    f"Covariance.matrix must be square with side {n}, got a row of length "
                    f"{len(row)}"
                )
            for entry in row:
                _check_finite_number(entry, label="Covariance.matrix entries")

        for i in range(n):
            for j in range(n):
                if not math.isclose(
                    self.matrix[i][j], self.matrix[j][i], rel_tol=1e-9, abs_tol=1e-12
                ):
                    raise ValueError(
                        "Covariance.matrix must be symmetric: "
                        f"matrix[{i}][{j}]={self.matrix[i][j]!r} != "
                        f"matrix[{j}][{i}]={self.matrix[j][i]!r}"
                    )

        if n > 0:
            matrix_arr = np.array(self.matrix, dtype=float)
            max_abs_entry = max(1.0, float(np.max(np.abs(matrix_arr))))
            min_eigenvalue = float(np.min(np.linalg.eigvalsh(matrix_arr)))
            tolerance = _POSITIVE_DEFINITE_RELATIVE_TOLERANCE * max_abs_entry
            if not min_eigenvalue > tolerance:
                raise ValueError(
                    "Covariance.matrix must be positive-definite: minimum eigenvalue "
                    f"{min_eigenvalue!r} does not exceed the tolerance {tolerance!r}"
                )


def _check_cluster_ids(cluster_ids: tuple[str | int, ...] | None, *, label: str) -> None:
    if cluster_ids is None:
        return
    if len(cluster_ids) == 0:
        raise ValueError(f"{label} must be non-empty when given, got an empty tuple")
    if len(set(cluster_ids)) != len(cluster_ids):
        raise ValueError(f"{label} must be unique, got {cluster_ids!r}")
    for cluster_id in cluster_ids:
        if cluster_id is None or isinstance(cluster_id, bool):
            raise ValueError(
                f"{label} elements must be a str or int, never None or bool, got {cluster_id!r}"
            )
        if not isinstance(cluster_id, (str, int)):
            raise ValueError(f"{label} elements must be a str or int, got {cluster_id!r}")


@dataclass(frozen=True, kw_only=True)
class Fit:
    """A dose-response fit, or an explicit record of why one was not obtained.

    The fitted curve (§5.1) is ``P(x) = u - (u - l) * F(z)``, where ``z = (log(x) - mu) / s`` on
    a log axis or ``z = (x - mu) / s`` on a linear axis, ``s > 0``, and ``F`` is the link's CDF
    (the standard normal CDF for ``probit``, the logistic CDF for ``logit``, or
    ``1 - exp(-exp(z))`` for ``cloglog``, which models the probability of *failure* rising with
    severity and so is not symmetric the way ``probit``/``logit`` are). ``mu`` is on the
    transformed axis (``log x`` on a log axis, ``x`` on a linear axis), not on the original
    severity scale. At ``z = 0`` -- severity ``exp(mu)`` on a log axis, or severity ``mu`` on a
    linear axis -- ``probit`` and ``logit`` both give ``P = (u + l) / 2``: the midpoint of the
    fitted dynamic range, :meth:`~marginkit.Definition.relative` ``(0.5)``, for **any**
    asymptotes ``u``, ``l``, because the standard normal and logistic CDFs each equal ``0.5``
    at ``z = 0``. That midpoint equals :meth:`~marginkit.Definition.absolute` ``(0.5)`` and
    :meth:`~marginkit.Definition.baseline_fraction` ``(0.5)`` only when ``u = 1`` and
    ``l = 0``. Under ``cloglog``, which is not symmetric around ``z = 0``,
    ``F(0) = 1 - exp(-1)`` (about ``0.632``), so ``mu`` is never the midpoint of the dynamic
    range, for any asymptotes. Each entry in ``params`` records whether it was held fixed or
    estimated, and is on the **natural scale**, never the optimiser's internal
    reparametrisation (``log s``; ``upper``/``lower`` on a logit scale) -- see
    :class:`Parameter`. ``covariance`` is on that same natural scale: when asymptotes are
    estimated, the optimiser's own covariance (which is on its reparametrised scale) is
    delta-transformed onto the natural scale before being stored here.

    ``status == Status.OK`` if and only if both ``params`` and ``log_likelihood`` are present;
    when ``status`` is anything else, ``params``, ``covariance`` and ``log_likelihood`` are all
    ``None`` -- no number is ever produced for a failed fit (hard constraint 3).
    ``Status.UNREACHABLE`` and ``Status.FAILS_AT_BASELINE`` describe a *threshold*, not a fit
    (they depend on a ``Definition`` a ``Fit`` does not have), and are never a ``Fit.status``.

    Binomial curves are decreasing-only in this release: ``direction="increasing"`` raises,
    pending owner decision D5's restatement of the definitions for an increasing-is-worse
    outcome (§5.3). ``Observations`` itself still accepts both directions.

    ``predict()`` (curve and band evaluation, R8) arrives in Phase 4. ``diagnostics``
    (goodness-of-fit, dispersion, monotonicity, link comparison, §5.7) arrives in Phase 7 as an
    appended field defaulting to ``None``, which is a safe addition under Appendix B.

    Attributes
    ----------
    axis
        The :class:`~marginkit.Axis` the fit was made on.
    outcome
        The outcome name this fit was made against, carried over from the
        :class:`~marginkit.Observations` it was fit to.
    direction
        ``"decreasing"`` only, in this release (see above).
    model
        The model family. Only ``"binomial"`` exists in v0.1 (schema ``"1"``); a new family
        such as ``"ll4"`` or ``"isotonic"`` is a v0.2 addition requiring ``schema_version``
        ``"2"``.
    link
        The link function: ``"probit"``, ``"logit"`` or ``"cloglog"`` for ``model="binomial"``.
        Required; the schema's ``link`` enum carries no ``null`` alternative, so this is a
        genuine ``str``, never ``None``.
    params
        A mapping with exactly the keys ``{"mu", "s", "upper", "lower"}`` when ``status`` is
        ``OK``, else ``None``. ``s.value`` must be positive; ``lower.value`` and
        ``upper.value`` must each lie in ``[0, 1]`` with ``lower.value < upper.value``.
        ``params["mu"].fixed`` and ``params["s"].fixed`` must both be ``False``: this package
        never produces (and this dataclass never accepts) an ``OK`` fit with a fixed location
        or scale.
    covariance
        The estimated parameters' covariance. Required (not ``None``) when ``status`` is
        ``OK``; ``None`` otherwise. If present, ``covariance.names`` is exactly the set of
        non-fixed parameter names.
    log_likelihood
        The fitted log-likelihood, or ``None`` when ``status`` is not ``OK``. Finite when
        present.
    cells
        The per-severity-level pooled counts the fit was made from
        (:meth:`~marginkit.Observations.cells`). Never empty.
    status
        The :class:`~marginkit.Status` of this fit. Never ``UNREACHABLE`` or
        ``FAILS_AT_BASELINE`` (those describe a threshold, not a fit).
    cluster_ids
        Optional cluster ids the fitted data carries, one instance per distinct cluster (not
        one per row): unique, non-empty when given, and never ``None`` or ``bool`` elements.
        Set whenever the input :class:`~marginkit.Observations` carried cluster ids, whatever
        dependence was assumed when this fit was produced -- this field reflects the data's
        structure, not a modelling choice. ``None`` means only that the data had no clusters,
        not that independence was assumed. Used by :class:`~marginkit.Ratio`'s dependence
        guard (§5.6).
    warnings
        Free-text notes surfaced alongside the fit (for example, ``CONTROL_INCOMPATIBLE``
        carries a message suggesting ``upper="estimate"``). Empty by default.
    schema_version
        The serialised-result schema version this object belongs to. Defaults to ``"1"``.
    provenance
        An opaque mapping the caller may attach to record where the inputs came from.
        marginkit stores it and never interprets it. Empty by default.
    """

    axis: Axis
    outcome: str
    direction: str
    model: str
    link: str
    params: Mapping[str, Parameter] | None
    covariance: Covariance | None
    log_likelihood: float | None
    cells: tuple[Cell, ...]
    status: Status
    cluster_ids: tuple[str | int, ...] | None = None
    warnings: tuple[str, ...] = ()
    schema_version: str = "1"
    provenance: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "cells", tuple(self.cells))
        if self.cluster_ids is not None:
            object.__setattr__(self, "cluster_ids", tuple(self.cluster_ids))

        if not self.outcome:
            raise ValueError("Fit.outcome must be non-empty")
        if self.direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"Fit.direction must be one of {sorted(_VALID_DIRECTIONS)}, got {self.direction!r}"
            )

        if self.model not in _VALID_MODELS:
            raise ValueError(
                f"Fit.model must be one of {sorted(_VALID_MODELS)}, got {self.model!r}"
            )
        if self.model == "binomial" and self.direction != "decreasing":
            raise ValueError(
                "Fit: model='binomial' only supports direction='decreasing' in this release; "
                "an increasing-is-worse definition is pending owner decision D5"
            )
        allowed_links = _VALID_LINKS[self.model]
        if self.link not in allowed_links:
            raise ValueError(
                f"Fit.link for model={self.model!r} must be one of {sorted(allowed_links)}, "
                f"got {self.link!r}"
            )

        if self.status in _INVALID_FIT_STATUSES:
            raise ValueError(
                f"Fit.status must not be {self.status!r}: that status describes a threshold, "
                "not a fit"
            )

        if not self.cells:
            raise ValueError("Fit.cells must not be empty")

        _check_cluster_ids(self.cluster_ids, label="Fit.cluster_ids")

        is_ok = self.status is Status.OK
        has_params = self.params is not None
        has_log_likelihood = self.log_likelihood is not None
        if is_ok != (has_params and has_log_likelihood):
            raise ValueError(
                "Fit.status is OK if and only if both params and log_likelihood are present: "
                f"status={self.status!r}, params is not None={has_params!r}, "
                f"log_likelihood is not None={has_log_likelihood!r}"
            )
        if not is_ok:
            if self.params is not None or self.covariance is not None:
                raise ValueError(
                    "Fit.params and Fit.covariance must both be None when status is not OK"
                )
            return

        if self.log_likelihood is not None:
            _check_finite_number(self.log_likelihood, label="Fit.log_likelihood")

        if self.covariance is None:
            raise ValueError("Fit.covariance is required when status is OK")

        params = self.params
        assert params is not None  # established by is_ok above
        if self.model == "binomial":
            if set(params) != _BINOMIAL_PARAM_NAMES:
                raise ValueError(
                    f"Fit.params for model='binomial' must have exactly the keys "
                    f"{sorted(_BINOMIAL_PARAM_NAMES)}, got {sorted(params)}"
                )
            if params["mu"].fixed or params["s"].fixed:
                raise ValueError(
                    "Fit.params['mu'].fixed and Fit.params['s'].fixed must both be False when "
                    "status is OK: this package never produces a fit with a fixed location or "
                    "scale (section 7)"
                )
            s = params["s"].value
            lower = params["lower"].value
            upper = params["upper"].value
            if not s > 0.0:
                raise ValueError(f"Fit.params['s'].value must be positive, got {s!r}")
            if not (0.0 <= lower < upper <= 1.0):
                raise ValueError(
                    "Fit.params must satisfy 0 <= lower.value < upper.value <= 1, got "
                    f"lower={lower!r}, upper={upper!r}"
                )

            if self.axis.scale == "log" and upper == 1.0 and params["upper"].fixed:
                for cell in self.cells:
                    if cell.severity == 0.0 and cell.successes < cell.trials:
                        raise ValueError(
                            "Fit: the zero-severity control has failures but 'upper' is fixed "
                            "at exactly 1.0, so the likelihood is zero for this fit on a log "
                            'axis; refit with upper="estimate" (section 5.1)'
                        )

        non_fixed = {name for name, param in params.items() if not param.fixed}
        if set(self.covariance.names) != non_fixed:
            raise ValueError(
                "Fit.covariance.names must equal the non-fixed parameter names: "
                f"expected {sorted(non_fixed)}, got {sorted(self.covariance.names)}"
            )
