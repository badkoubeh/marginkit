"""``Status``/``Censoring`` member coverage for ``threshold()`` that the committed zeta matrix
(``tests/unit/test_threshold_zeta.py``) does not reach on its own: ``CONTROL_INCOMPATIBLE``,
``NOT_CONVERGED``, both ``UNREACHABLE`` routes (`docs/decisions/0008`), the ordering rule between
``FAILS_AT_BASELINE`` and ``UNREACHABLE`` when both apply to the same fit, and
``OPEN_UPPER``/``OPEN_LOWER``.

Every dataset here is constructed, not drawn from ``zeta_matrix_counts.csv`` -- each is chosen
because the *real*, already-shipped Phase 4 ``fit_dose_response`` (confirmed empirically, not
assumed) produces the fit status the corresponding ``threshold()`` case needs, so this file is
still checking real fit behaviour, only not real-world data.
"""

from __future__ import annotations

import json
from pathlib import Path

from marginkit import Axis, Definition, Observations, Status, fit_dose_response, threshold
from marginkit.types import Censoring

_LEVEL = 0.95
_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tools" / "drc_reference"


class TestControlIncompatible:
    """A fixed ``upper=1.0`` with a failing zero-severity control drives the likelihood to zero
    on a log axis (plan section 5.1); ``fit_dose_response`` reports
    ``Status.CONTROL_INCOMPATIBLE`` before ever attempting to fit (confirmed:
    ``tests/unit/test_models_zeta.py::test_sac_sensor_noise_u_1_is_control_incompatible``, on
    the same ``sac_sensor_noise`` counts reused here).
    """

    def test_threshold_mirrors_control_incompatible_with_no_numbers(self) -> None:
        axis = Axis(name="sensor_noise", unit="m", scale="log")
        obs = Observations.from_counts(
            axis,
            severity=[0.0, 0.01, 0.05, 0.1],
            successes=[98, 0, 0, 0],
            trials=[200, 300, 300, 300],
            outcome="success",
            direction="decreasing",
        )
        fit = fit_dose_response(obs, model="binomial", link="probit", upper=1.0, lower=0.0)
        assert fit.status is Status.CONTROL_INCOMPATIBLE

        t = threshold(
            fit, definition=Definition.absolute(0.95), interval_method="profile", level=_LEVEL
        )

        assert t.status is fit.status is Status.CONTROL_INCOMPATIBLE
        assert t.censoring is Censoring.NONE
        assert t.value is None and t.lo is None and t.hi is None
        assert t.interval_method == "exact_bound"
        assert t.baseline is None


class TestNotConverged:
    """A dataset with a decreasing-but-shallow success rate and an *estimated* upper asymptote
    that genuinely fails to converge under Phase 4's likelihood path (confirmed empirically:
    ``fit_dose_response`` on this exact data returns ``Status.NOT_CONVERGED`` with 'the
    optimizer did not converge' in ``warnings`` -- this is not the separation/control-
    incompatible pre-fit check, it is the post-fit convergence check, decisions/0005).
    """

    def test_threshold_mirrors_not_converged_with_grid_attached(self) -> None:
        axis = Axis(name="not_converged_probe", unit="unit", scale="log")
        obs = Observations.from_counts(
            axis,
            severity=[0.0, 1.0, 2.0, 4.0],
            successes=[40, 35, 25, 10],
            trials=[100, 100, 100, 100],
            outcome="success",
            direction="decreasing",
        )
        fit = fit_dose_response(obs, model="binomial", link="probit", upper="estimate", lower=0.0)
        assert fit.status is Status.NOT_CONVERGED
        assert any("did not converge" in w for w in fit.warnings)

        # The target must clear the control, or `FAILS_AT_BASELINE` short-circuits ahead of the
        # fallback this test is about (`decisions/0008` fixes that order). The control is
        # 40/100, whose one-sided upper bound at 0.95 is 0.4870, so `absolute(0.5)` -- the
        # target this probe first used -- is one the control already provably fails. 0.3 clears
        # it and reaches the NOT_CONVERGED path.
        t = threshold(
            fit, definition=Definition.absolute(0.3), interval_method="profile", level=_LEVEL
        )

        assert t.status is fit.status is Status.NOT_CONVERGED
        assert t.value is None
        assert t.interval_method == "exact_bound"
        assert t.censoring in (Censoring.NONE, Censoring.RIGHT, Censoring.LEFT)
        # decisions/0010: grid is set on every SEPARATION/NOT_CONVERGED exact-bound fallback.
        assert t.grid is not None


class TestUnreachableAboveAFixedCeiling:
    """``absolute(a)`` with ``a`` at or beyond the fitted ``upper`` asymptote (decisions/0008:
    reachability requires ``l < P* < u`` for *every* definition, not only ``absolute``). Uses a
    ``upper=0.9`` **fixed** (rather than estimated) ceiling: decisions/0008's reachability check
    reads ``fit.params["upper"].value`` the same way regardless of whether that parameter was
    fixed or estimated, so a fixed ceiling exercises the identical branch far more
    deterministically than coaxing a specific estimated value out of an optimizer, while control
    still clears the target easily (so this is not also ``FAILS_AT_BASELINE`` -- see
    ``TestFailsAtBaselineWinsOverUnreachable`` below for that combination).
    """

    def test_absolute_0_95_is_unreachable_when_upper_is_fixed_at_0_9(self) -> None:
        axis = Axis(name="unreachable_probe", unit="unit", scale="log")
        obs = Observations.from_counts(
            axis,
            severity=[0.0, 0.5, 1.0, 2.0],
            successes=[100, 70, 50, 10],
            trials=[100, 100, 100, 100],
            outcome="success",
            direction="decreasing",
        )
        fit = fit_dose_response(obs, model="binomial", link="probit", upper=0.9, lower=0.0)
        assert fit.status is Status.OK
        assert fit.params is not None
        assert fit.params["upper"].value == 0.9
        assert fit.params["upper"].fixed is True

        t = threshold(
            fit, definition=Definition.absolute(0.95), interval_method="profile", level=_LEVEL
        )

        assert t.status is Status.UNREACHABLE
        assert t.censoring is Censoring.NONE
        assert t.value is None and t.lo is None and t.hi is None
        assert t.interval_method == "exact_bound"
        assert t.baseline is None
        assert t.grid is None


class TestUnreachableBaselineFractionBelowTheFloor:
    """``baseline_fraction(p)`` is unreachable whenever ``p * u <= l`` (decisions/0008) -- the
    target fraction of the control's own performance sits at or below the fitted floor. Uses
    both asymptotes fixed (``upper=0.9, lower=0.2``) for the same determinism reason as
    ``TestUnreachableAboveAFixedCeiling``: ``p=0.1`` gives a target of ``0.1 * 0.9 = 0.09``,
    below the fixed floor of ``0.2``.
    """

    def test_baseline_fraction_0_1_is_unreachable_when_p_times_u_is_at_or_below_l(self) -> None:
        axis = Axis(name="baseline_fraction_unreachable_probe", unit="unit", scale="log")
        obs = Observations.from_counts(
            axis,
            severity=[0.0, 0.5, 1.0, 2.0],
            successes=[90, 70, 50, 25],
            trials=[100, 100, 100, 100],
            outcome="success",
            direction="decreasing",
        )
        fit = fit_dose_response(obs, model="binomial", link="probit", upper=0.9, lower=0.2)
        assert fit.status is Status.OK
        assert fit.params is not None
        assert fit.params["lower"].value == 0.2
        assert fit.params["upper"].value == 0.9

        t = threshold(
            fit,
            definition=Definition.baseline_fraction(0.1),
            interval_method="profile",
            level=_LEVEL,
        )

        assert t.status is Status.UNREACHABLE
        assert t.censoring is Censoring.NONE
        assert t.value is None and t.lo is None and t.hi is None
        assert t.interval_method == "exact_bound"


class TestFailsAtBaselineWinsOverUnreachable:
    """decisions/0008's ordering regression test: when the control already fails the criterion
    *and* the (independently, genuinely fitted) asymptote also cannot reach it, decisions/0008
    says ``FAILS_AT_BASELINE`` wins -- it rests on the sharper, exact test of the raw control
    cell, not on the fitted asymptote.

    Uses the committed ``tools/drc_reference/estimated_asymptotes.json`` simulation (true
    ``upper=0.9``, control 365/400) rather than any zeta-bench series: every zeta ``sensor_noise``
    series' ``upper="estimate"`` fit is ``Status.SEPARATION`` (confirmed:
    ``tests/unit/test_models_zeta.py``'s own ``..._upper_estimate_is_separation`` tests, for
    every one of PID/SAC/PPO), and decisions/0008 says the reachability check *cannot run* on a
    fit with no fitted parameters at all ("the reachability check needs l and u, so it cannot
    run on the fallback path") -- so no zeta series can exercise the actual UNREACHABLE-vs-
    FAILS_AT_BASELINE conflict this test targets. This fixture's simulated data genuinely
    converges (confirmed empirically: ``fit_dose_response`` on it with
    ``upper="estimate", lower=0.0`` gives ``Status.OK`` with ``upper`` estimated at about
    ``0.928``), and its control (365/400 = 0.9125) has an exact one-sided 95% upper bound of
    about ``0.935`` -- below ``0.95`` -- so ``absolute(0.95)`` is *both* ``FAILS_AT_BASELINE``
    (the control fails outright) *and* would independently be ``UNREACHABLE`` (the fitted
    ceiling, ~0.928, also cannot reach 0.95).
    """

    def test_absolute_0_95_is_fails_at_baseline_not_unreachable(self) -> None:
        with (_FIXTURE_DIR / "estimated_asymptotes.json").open() as fh:
            fixture = json.load(fh)
        sim = fixture["simulation"]
        axis = Axis(name="severity", unit="unit", scale="log")
        obs = Observations.from_counts(
            axis,
            severity=sim["severity"],
            successes=sim["successes"],
            trials=sim["trials"],
            outcome="success",
            direction="decreasing",
        )
        fit = fit_dose_response(obs, model="binomial", link="probit", upper="estimate", lower=0.0)
        assert fit.status is Status.OK
        assert fit.params is not None
        # Both preconditions for the ordering conflict, made explicit rather than assumed.
        assert fit.params["upper"].value < 0.95, (
            "fixture drifted: this test needs the fitted ceiling below the 0.95 criterion"
        )

        t = threshold(
            fit, definition=Definition.absolute(0.95), interval_method="profile", level=_LEVEL
        )

        assert t.status is Status.FAILS_AT_BASELINE
        assert t.status is not Status.UNREACHABLE
        assert t.baseline is not None
        assert t.baseline.successes == 365
        assert t.baseline.trials == 400


class TestOpenSidedProfileCensoring:
    """``OPEN_UPPER``/``OPEN_LOWER`` (plan section 5.5): the value lies inside the tested range,
    but one side of its profile interval does not close within the search limit (plan section
    5.4: ``log(100)`` beyond the tested range). Tried as a small set of weakly-identified
    candidate designs (two close, well-sampled nonzero levels anchoring the crossing tightly on
    one side, plus a third, very-low-sample level placed far out on the other) rather than one
    specific number, because the exact numeric boundary of "does not close" depends on
    ``threshold()``'s own root-finding, which did not exist yet to verify a single specific
    dataset against when this test was written (plan section 6: tests before implementation).

    If none of these candidates trigger ``OPEN_UPPER``/``OPEN_LOWER`` once ``threshold()``
    exists, that is a finding about *this test's* construction -- report it and replace the
    candidate list with one searched against the real implementation, rather than deleting the
    coverage requirement.
    """

    _CANDIDATES: tuple[tuple[list[float], list[int], list[int]], ...] = (
        ([0.0, 1.0, 1.5, 500.0], [100, 90, 40, 1], [100, 100, 100, 2]),
        ([0.0, 1.0, 1.2, 800.0], [100, 95, 30, 0], [100, 100, 100, 1]),
        ([0.0, 2.0, 2.5, 1000.0], [100, 85, 45, 1], [100, 100, 100, 3]),
    )

    def test_at_least_one_candidate_design_leaves_one_profile_side_open(self) -> None:
        axis = Axis(name="open_interval_probe", unit="unit", scale="log")
        found: Censoring | None = None

        for severity, successes, trials in self._CANDIDATES:
            obs = Observations.from_counts(
                axis,
                severity=severity,
                successes=successes,
                trials=trials,
                outcome="success",
                direction="decreasing",
            )
            fit = fit_dose_response(obs, model="binomial", link="probit", upper=1.0, lower=0.0)
            if fit.status is not Status.OK:
                continue
            t = threshold(
                fit,
                definition=Definition.absolute(0.5),
                interval_method="profile",
                level=_LEVEL,
            )
            if t.censoring in (Censoring.OPEN_UPPER, Censoring.OPEN_LOWER):
                found = t.censoring
                if found is Censoring.OPEN_UPPER:
                    assert t.value is not None and t.lo is not None and t.hi is None
                else:
                    assert t.value is not None and t.hi is not None and t.lo is None
                assert t.status is Status.OK
                break

        assert found is not None, (
            "none of the constructed candidate designs produced OPEN_UPPER/OPEN_LOWER against "
            "the real threshold() implementation; this test's candidate list needs revisiting "
            "(plan section 5.4's search-limit behaviour was unverified when it was written)"
        )
