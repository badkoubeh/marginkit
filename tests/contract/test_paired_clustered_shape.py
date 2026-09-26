"""Contract test: the per-unit, clustered call shape marginbench uses.

Mirrors marginbench's shape (plan section 3.1): per-scenario, per-seed binary outcomes over a
log-spaced severity grid plus a zero-severity control, with the same scenario ids recurring at
every level -- clustered, not independent. Only the public API surface is used here -- no
internal marginkit module is imported.

A failing **live** test in this file means a breaking change to the public API marginbench
depends on (plan section 3.3, ``docs/CONSUMERS.md``). **Do not edit a live test to make it
pass.** Stop and ask; that failure is the signal a breaking change needs owner sign-off.

**``test_paired_ratio_between_two_thresholds_on_the_same_clustered_fit`` was still marked
``xfail(strict=True, raises=ImportError)`` after ``ratio_interval`` started existing (Phase 6),
and its premise had expired without anyone noticing** -- exactly the kind of drift a strict
``xfail`` is supposed to catch, and did: ``threshold(fit, ...)`` at what is now line ~130 is
called with no ``dependence=`` argument, and ``fit`` here carries cluster ids (the whole point of
this file), so R2's guard (a method assuming independence must refuse clustered input unless the
caller opts in explicitly) raises ``ValueError`` there, before the test ever reaches the
``dependence="paired"`` call it exists to exercise. That is not the breaking change the module's
own rule above warns against -- it is a stale ``xfail`` reason (written when ``threshold()``
did not exist at all) outliving the code path it described, not a live contract regressing. The
fix threads ``dependence="independent"`` through both ``threshold()`` calls (acknowledging
independence is being assumed for *those* calls, same as any other caller with clustered data),
which lets the test reach the actual ``ratio_interval(..., dependence="paired")`` call and assert
what it always meant to: that a v0.2 feature requested early raises ``ValueError``, per
``threshold()``'s own existing precedent for the same request and
``tests/unit/test_ratio_interval_guards.py::TestPairedDependenceNotImplemented``.
"""

from __future__ import annotations

import pytest

from marginkit import Axis, Cell, Observations

_AXIS = Axis(name="noise", unit="ratio", scale="log")

# Nine log-spaced severities (0.01 doubling up to 1.0) plus the zero control, four scenario ids
# repeated at every level so the design is clustered rather than independent (plan section 3.1's
# marginbench row: "clustered by scenario, paired outcomes"). The pass counts per level are a
# fixed, hand-written schedule, not drawn from any random source, so there is no hidden
# randomness here to pin a seed for.
_SEVERITIES: tuple[float, ...] = (0.0, 0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.0)
_SCENARIOS: tuple[str, ...] = ("scenario_a", "scenario_b", "scenario_c", "scenario_d")
_PASSING_SCENARIOS_PER_LEVEL: tuple[int, ...] = (4, 4, 3, 3, 2, 2, 1, 1, 0)


def _clustered_rows() -> tuple[tuple[float, ...], tuple[int, ...], tuple[str, ...]]:
    """Build per-unit ``(severity, success, cluster)`` rows for the fixture above."""
    severity: list[float] = []
    success: list[int] = []
    cluster: list[str] = []
    for level, n_passing in zip(_SEVERITIES, _PASSING_SCENARIOS_PER_LEVEL, strict=True):
        for index, scenario in enumerate(_SCENARIOS):
            severity.append(level)
            success.append(1 if index < n_passing else 0)
            cluster.append(scenario)
    return tuple(severity), tuple(success), tuple(cluster)


def test_from_observations_with_cluster_ids_marks_observations_as_clustered() -> None:
    severity, success, cluster = _clustered_rows()

    obs = Observations.from_observations(
        _AXIS,
        severity=severity,
        success=success,
        outcome="consistent",
        direction="decreasing",
        cluster=cluster,
    )

    assert obs.is_clustered is True
    assert obs.cluster == cluster


def test_clustered_observations_cells_totals_match_the_per_level_schedule() -> None:
    severity, success, cluster = _clustered_rows()

    obs = Observations.from_observations(
        _AXIS,
        severity=severity,
        success=success,
        outcome="consistent",
        direction="decreasing",
        cluster=cluster,
    )

    expected = tuple(
        Cell(severity=level, successes=n_passing, trials=len(_SCENARIOS))
        for level, n_passing in zip(_SEVERITIES, _PASSING_SCENARIOS_PER_LEVEL, strict=True)
    )
    assert obs.cells() == expected


def test_threshold_on_clustered_input_without_independent_dependence_raises() -> None:
    """R2: a method that assumes independence must refuse clustered input outright."""
    from marginkit import Definition, fit_dose_response, threshold

    severity, success, cluster = _clustered_rows()
    obs = Observations.from_observations(
        _AXIS,
        severity=severity,
        success=success,
        outcome="consistent",
        direction="decreasing",
        cluster=cluster,
    )
    fit = fit_dose_response(obs, model="binomial", link="probit", upper=1.0, lower=0.0)

    with pytest.raises(ValueError):
        threshold(fit, definition=Definition.absolute(0.5), interval_method="profile", level=0.95)


def test_paired_ratio_between_two_thresholds_on_the_same_clustered_fit_is_not_implemented() -> None:
    """v0.2, plan D6/section 5.6: outcomes measured on the same inferences need
    ``dependence="paired"``, not ``"independent"``, because independence is the wrong
    assumption for a shared-cluster design -- not implemented until v0.2 Phase 9, so
    ``ratio_interval`` must raise rather than silently falling back to treating the pair as
    independent.

    ``dependence="independent"`` is passed to both ``threshold()`` calls (module docstring):
    R2's clustered-input guard would otherwise raise here, before ever reaching the
    ``dependence="paired"`` call this test exists to check.
    """
    from marginkit import Definition, fit_dose_response, ratio_interval, threshold

    severity, success, cluster = _clustered_rows()
    obs = Observations.from_observations(
        _AXIS,
        severity=severity,
        success=success,
        outcome="consistent",
        direction="decreasing",
        cluster=cluster,
    )
    fit = fit_dose_response(obs, model="binomial", link="probit", upper=1.0, lower=0.0)
    t_a = threshold(
        fit,
        definition=Definition.absolute(0.5),
        interval_method="profile",
        level=0.95,
        dependence="independent",
    )
    t_b = threshold(
        fit,
        definition=Definition.baseline_fraction(0.5),
        interval_method="profile",
        level=0.95,
        dependence="independent",
    )

    with pytest.raises(ValueError):
        ratio_interval(t_a, t_b, method="fieller", dependence="paired")
