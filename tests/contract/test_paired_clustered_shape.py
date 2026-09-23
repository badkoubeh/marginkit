"""Contract test: the per-unit, clustered call shape marginbench uses.

Mirrors marginbench's shape (plan section 3.1): per-scenario, per-seed binary outcomes over a
log-spaced severity grid plus a zero-severity control, with the same scenario ids recurring at
every level -- clustered, not independent. Only the public API surface is used here -- no
internal marginkit module is imported.

A failing **live** test in this file means a breaking change to the public API marginbench
depends on (plan section 3.3, ``docs/CONSUMERS.md``). **Do not edit a live test to make it
pass.** Stop and ask; that failure is the signal a breaking change needs owner sign-off. The two
``xfail`` tests below are different: they exercise API that does not exist yet (``threshold()``
until Phase 5, ``dependence="paired"`` until v0.2 Phase 9). The first now fails with
``TypeError``, not ``ImportError``: since Phase 4 added ``fit_dose_response``,
``from marginkit import threshold`` no longer errors on import -- it binds the
``marginkit.threshold`` submodule (imported as a side effect of ``marginkit/__init__.py``),
which is not callable, so the ``TypeError`` comes from calling it. The second still imports
``ratio_interval``, which genuinely does not exist as any attribute, so it still fails with
``ImportError``.
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


@pytest.mark.xfail(
    strict=True,
    raises=ImportError,
    reason="v0.2 Phase 9: dependence='paired' does not exist until Phase 9",
)
def test_paired_ratio_between_two_thresholds_on_the_same_clustered_fit() -> None:
    """v0.2, plan D6/section 5.6: outcomes measured on the same inferences need
    ``dependence="paired"``, not ``"independent"``, because independence is the wrong
    assumption for a shared-cluster design."""
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
    t_a = threshold(fit, definition=Definition.absolute(0.5), interval_method="profile", level=0.95)
    t_b = threshold(
        fit, definition=Definition.baseline_fraction(0.5), interval_method="profile", level=0.95
    )

    ratio_interval(t_a, t_b, method="fieller", dependence="paired")
