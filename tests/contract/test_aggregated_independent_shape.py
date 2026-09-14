"""Contract test: the aggregated, independent call shape zeta-bench uses.

Mirrors how zeta-bench's ``robustness/cards.py`` calls the ported grid rule: a degradation
curve as a list of ``(severity, success_rate)`` pairs, unzipped into two lists, run through
the public API with ``criterion=0.95, signed=True``, then read back via ``.value`` and
``.max_tested`` (see ``build_card_summary`` / ``_format_break`` in
``../zeta-bench/robustness/cards.py``). Only the public API surface is used here — no internal
marginkit module is imported.

A failing test in this file means a breaking change to the public API that zeta-bench depends
on (plan section 3.3, ``docs/CONSUMERS.md``). **Do not edit this test to make it pass.** Stop
and ask; that failure is the signal a breaking change needs owner sign-off.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from inspect import Parameter

from marginkit import Censoring, grid_break_point


def test_zeta_bench_shaped_call_reads_value_and_max_tested() -> None:
    """Unzip a ``(severity, rate)`` curve, call with keyword ``criterion``, read the result."""
    curve: list[tuple[float, float]] = [
        (-0.2, 0.05),
        (-0.1, 0.77),
        (0.0, 0.99),
        (0.1, 0.33),
        (0.2, 0.0),
    ]
    severity, rate = zip(*curve)

    result = grid_break_point(list(severity), list(rate), criterion=0.95, signed=True)

    assert result.value == 0.1
    assert result.max_tested == 0.2


def test_zeta_bench_shaped_call_reports_right_censoring_as_none_value() -> None:
    """When the gate holds everywhere, ``.value`` is ``None`` and ``.max_tested`` is the bound.

    This is the shape zeta-bench's ``_format_break`` relies on: ``bp is None`` selects the
    "holds <= max tested" wording rather than a numeric break-point.
    """
    curve: list[tuple[float, float]] = [(0.0, 1.0), (2.0, 1.0), (5.0, 1.0), (10.0, 1.0)]
    severity, rate = zip(*curve)

    result = grid_break_point(list(severity), list(rate), criterion=0.95, signed=True)

    assert result.value is None
    assert result.max_tested == 10.0


def test_censoring_has_exactly_the_five_documented_members() -> None:
    """The tag freezes at ``v0.1.0a1``: no member added, removed, or renamed after that."""
    members = {member.name: member.value for member in Censoring}

    assert members == {
        "NONE": "NONE",
        "RIGHT": "RIGHT",
        "LEFT": "LEFT",
        "OPEN_UPPER": "OPEN_UPPER",
        "OPEN_LOWER": "OPEN_LOWER",
    }


def test_zeta_bench_shaped_call_reports_censoring_none_when_curve_fails() -> None:
    curve: list[tuple[float, float]] = [
        (-0.2, 0.05),
        (-0.1, 0.77),
        (0.0, 0.99),
        (0.1, 0.33),
        (0.2, 0.0),
    ]
    severity, rate = zip(*curve)

    result = grid_break_point(list(severity), list(rate), criterion=0.95, signed=True)

    assert result.censoring is Censoring.NONE


def test_zeta_bench_shaped_call_reports_censoring_right_with_none_value_when_curve_holds() -> None:
    curve: list[tuple[float, float]] = [(0.0, 1.0), (2.0, 1.0), (5.0, 1.0), (10.0, 1.0)]
    severity, rate = zip(*curve)

    result = grid_break_point(list(severity), list(rate), criterion=0.95, signed=True)

    assert result.censoring is Censoring.RIGHT
    assert result.value is None


def test_result_round_trips_through_json_with_string_censoring_and_schema_version() -> None:
    curve: list[tuple[float, float]] = [
        (-0.2, 0.05),
        (-0.1, 0.77),
        (0.0, 0.99),
        (0.1, 0.33),
        (0.2, 0.0),
    ]
    severity, rate = zip(*curve)
    result = grid_break_point(list(severity), list(rate), criterion=0.95, signed=True)

    dumped = json.dumps(dataclasses.asdict(result))
    reloaded = json.loads(dumped)

    assert reloaded["censoring"] in ("NONE", "RIGHT")
    assert reloaded["censoring"] == "NONE"
    assert reloaded["schema_version"] == "1"


def test_right_censored_result_round_trips_through_json_too() -> None:
    curve: list[tuple[float, float]] = [(0.0, 1.0), (2.0, 1.0), (5.0, 1.0), (10.0, 1.0)]
    severity, rate = zip(*curve)
    result = grid_break_point(list(severity), list(rate), criterion=0.95, signed=True)

    dumped = json.dumps(dataclasses.asdict(result))
    reloaded = json.loads(dumped)

    assert reloaded["censoring"] == "RIGHT"
    assert reloaded["schema_version"] == "1"


def test_criterion_is_keyword_only_and_signed_defaults_to_false() -> None:
    signature = inspect.signature(grid_break_point)

    assert signature.parameters["criterion"].kind is Parameter.KEYWORD_ONLY
    assert signature.parameters["signed"].default is False
