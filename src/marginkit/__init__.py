"""Robustness-margin estimation: thresholds with confidence intervals.

marginkit's break-point and censoring **conventions** come from zeta-bench
(``robustness/cards.py::break_point``). Its dose-response **estimation is new**. See
``docs/PROVENANCE.md``.

As of ``0.1.0a1`` only the grid break-point rule (:func:`grid_break_point`, returning
:class:`GridBreakPoint`) and the :class:`Censoring` enum are exported. They were exported ahead
of the rest of the API so that the first consumer can depend on them. The model fit,
thresholds, and ratios are not part of this release.
"""

from __future__ import annotations

from marginkit.empirical import GridBreakPoint, grid_break_point
from marginkit.types import Censoring

__version__ = "0.1.0a1"

__all__ = [
    "Censoring",
    "GridBreakPoint",
    "__version__",
    "grid_break_point",
]
