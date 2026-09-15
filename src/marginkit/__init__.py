"""Robustness-margin estimation: thresholds with confidence intervals.

marginkit's break-point and censoring **conventions** come from zeta-bench
(``robustness/cards.py::break_point``). Its dose-response **estimation is new**. See
``docs/PROVENANCE.md``.

As of ``0.1.0a2`` this package exports the full v1 contract: the vocabulary types
(:class:`Axis`, :class:`Observations`, :class:`Definition`, :class:`Cell`), the status and
interval-shape enums (:class:`Status`, :class:`IntervalShape`, alongside the existing
:class:`Censoring`), the result dataclasses (:class:`Fit`, :class:`Threshold`, :class:`Ratio`,
:class:`Scorecard`), and the grid break-point rule (:func:`grid_break_point`, returning
:class:`GridBreakPoint`). The JSON report module (``marginkit.report``) and the schema-valid
test fakes (``marginkit.testing``) are importable as submodules but are not re-exported here.

Fitting a dose-response curve, solving for a threshold, and computing a ratio interval are
**not part of this release**: there is no ``fit_dose_response``, ``threshold`` or
``ratio_interval`` yet, only the result types those functions will return. They arrive in
Phases 4-6.
"""

from __future__ import annotations

from marginkit.empirical import GridBreakPoint, grid_break_point
from marginkit.models import Covariance, Fit, Parameter
from marginkit.ratio import Ratio
from marginkit.report import Scorecard
from marginkit.threshold import Threshold
from marginkit.types import (
    Axis,
    Cell,
    Censoring,
    Definition,
    IntervalShape,
    Observations,
    Status,
)

__version__ = "0.1.0a2"

__all__ = [
    "Axis",
    "Cell",
    "Censoring",
    "Covariance",
    "Definition",
    "Fit",
    "GridBreakPoint",
    "IntervalShape",
    "Observations",
    "Parameter",
    "Ratio",
    "Scorecard",
    "Status",
    "Threshold",
    "__version__",
    "grid_break_point",
]
