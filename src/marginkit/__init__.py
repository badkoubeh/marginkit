"""Robustness-margin estimation: thresholds with confidence intervals.

marginkit's break-point and censoring **conventions** come from zeta-bench
(``robustness/cards.py::break_point``). Its dose-response **estimation is new**. See
``docs/PROVENANCE.md``.

As of ``0.1.0a2`` this package exports the full v1 contract: the vocabulary types
(:class:`Axis`, :class:`Observations`, :class:`Definition`, :class:`Cell`), the status and
interval-shape enums (:class:`Status`, :class:`IntervalShape`, alongside the existing
:class:`Censoring`), the result dataclasses (:class:`Fit`, :class:`Threshold`, :class:`Ratio`,
:class:`Scorecard`), the grid break-point rule (:func:`grid_break_point`, returning
:class:`GridBreakPoint`), and the dose-response fitter (:func:`fit_dose_response`, returning a
:class:`Fit` whose :meth:`~Fit.predict` returns a :class:`Prediction`). The JSON report module
(``marginkit.report``) and the schema-valid test fakes (``marginkit.testing``) are importable
as submodules but are not re-exported here.

As of ``0.1.0a3`` this release adds :func:`threshold`, which solves for the severity at which
a fitted curve crosses a target performance and attaches an interval or an explicit censoring
label (plan §5.3-§5.5), together with :class:`BaselineRate`, :class:`ExactRates` and
:func:`per_cell_clopper_pearson`.

As of ``0.1.0a4`` this release adds :func:`ratio_interval`, which solves for the ratio of two
thresholds' severities with a Fieller or log-delta confidence interval (plan §5.6).

Note that ``marginkit.threshold`` is now the *function*, not the submodule.
"""

from __future__ import annotations

from marginkit.empirical import (
    BaselineRate,
    ExactRates,
    GridBreakPoint,
    grid_break_point,
    per_cell_clopper_pearson,
)
from marginkit.models import Covariance, Fit, Parameter, Prediction, fit_dose_response
from marginkit.ratio import Ratio, ratio_interval
from marginkit.report import Scorecard
from marginkit.threshold import Threshold, threshold
from marginkit.types import (
    Axis,
    Cell,
    Censoring,
    Definition,
    IntervalShape,
    Observations,
    Status,
)

__version__ = "0.1.0a4"

__all__ = [
    "Axis",
    "BaselineRate",
    "Cell",
    "Censoring",
    "Covariance",
    "Definition",
    "ExactRates",
    "Fit",
    "GridBreakPoint",
    "IntervalShape",
    "Observations",
    "Parameter",
    "Prediction",
    "Ratio",
    "Scorecard",
    "Status",
    "Threshold",
    "__version__",
    "fit_dose_response",
    "grid_break_point",
    "per_cell_clopper_pearson",
    "ratio_interval",
    "threshold",
]
