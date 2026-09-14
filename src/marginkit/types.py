"""marginkit's shared vocabulary for severity and outcome data.

Only :class:`Censoring` is defined here so far. The rest of the vocabulary this module will
hold (axes, observations, threshold definitions, and the status and interval-shape enums) is
not part of this release.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Censoring"]


class Censoring(StrEnum):
    """How a result's tested range relates to a criterion.

    Every member is a ``str`` subclass whose value equals its member name (``Censoring.RIGHT
    == "RIGHT"``). That value is the literal string a serialised result writes for this field,
    not an incidental implementation detail.

    **Model-based thresholds** use the full classification. It assumes performance is
    monotone in severity, and a result that uses it says so. ``RIGHT`` and ``LEFT`` are decided
    by exact one-sided tests at the edge of the tested range, not by point estimates.

    **The grid rule** (:func:`marginkit.grid_break_point`) uses only ``NONE`` and ``RIGHT``, and
    only as point-estimate labels, with no exact test and no monotonicity assumption. Their
    meaning for a grid result is documented on :class:`marginkit.GridBreakPoint` and is weaker
    than the definitions below.

    Attributes
    ----------
    NONE
        Model-based threshold: none of the conditions below applies, so a value is reported
        with both interval sides closed. Grid result: at least one tested level failed. This
        does not imply the criterion was bracketed.
    RIGHT
        Model-based threshold: the exact one-sided bound at the highest tested level shows the
        criterion still holds there. No value is reported. The top of the tested range is
        reported as a one-sided lower bound ("held up to the highest level tested") and is
        never phrased as "does not fail" or "unbreakable". Grid result: no tested level's
        performance fell below the criterion.
    LEFT
        Model-based threshold: the exact one-sided bound at the lowest nonzero tested level
        shows it already fails, while the control passes. No value is reported. The lowest
        nonzero level is reported as a one-sided upper bound. Never produced by the grid rule.
    OPEN_UPPER
        Model-based threshold: the value lies inside the tested range, but the upper side of
        its profile interval does not close within the search limit. The value and the closed
        lower side are still reported. Never produced by the grid rule.
    OPEN_LOWER
        The mirror of ``OPEN_UPPER``: the lower side of the profile interval does not close
        within the search limit. The value and the closed upper side are still reported. Never
        produced by the grid rule.
    """

    NONE = "NONE"
    RIGHT = "RIGHT"
    LEFT = "LEFT"
    OPEN_UPPER = "OPEN_UPPER"
    OPEN_LOWER = "OPEN_LOWER"
