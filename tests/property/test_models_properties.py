"""Property tests for ``fit_dose_response`` (plan section 6.4; hypothesis).

Four properties, matching the test-author brief and the Phase 4 plan's Files table:

- Aggregated counts give a fit identical to the equivalent ``from_observations`` rows (R1).
- Row permutation changes nothing.
- With ``u=1`` fixed, adding an all-success control row leaves the fit unchanged.
- On a log axis, ``x -> c*x`` shifts ``mu`` by ``log(c)`` and leaves ``s`` unchanged.

The first two do **not** require the fit to converge: two representations of *exactly the same
counts* must give exactly the same ``Fit`` -- including when that fit fails, since
``fit_dose_response`` is a deterministic function of the pooled cell counts (R1's own wording),
not of row order or representation. The third and fourth properties are about what a
**successful** fit does, so they use ``hypothesis.assume`` to skip examples that do not
converge, after choosing strategies designed to make that the common case (per the brief:
"keep designs non-separated").

Examples are kept small (few levels, small trial counts) so real optimizer calls stay fast, per
the brief.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from marginkit import Axis, Fit, Observations, Status, fit_dose_response

_MAX_EXAMPLES = 25
_AXIS = Axis(name="severity", unit="unit", scale="log")


@st.composite
def _counts_with_optional_control(
    draw: st.DrawFn,
) -> tuple[list[float], list[int], list[int]]:
    """A small counts table with at least one nonzero severity, and optionally an exact-zero
    control, so ``fit_dose_response`` always has something to fit on (log axis).
    """
    has_control = draw(st.booleans())
    n_nonzero = draw(st.integers(min_value=1, max_value=4))
    nonzero_severities = draw(
        st.lists(
            st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False),
            min_size=n_nonzero,
            max_size=n_nonzero,
            unique=True,
        )
    )
    severities = ([0.0] if has_control else []) + nonzero_severities
    trials = draw(
        st.lists(
            st.integers(min_value=5, max_value=50),
            min_size=len(severities),
            max_size=len(severities),
        )
    )
    successes = [draw(st.integers(min_value=0, max_value=t)) for t in trials]
    return severities, successes, trials


@st.composite
def _non_separated_counts(draw: st.DrawFn) -> tuple[list[float], list[int], list[int]]:
    """A counts table with **every** level carrying at least one success and one failure
    (strictly interior counts), which makes plan section 5.2's pre-fit separation check
    provably never trigger: with every level contributing both a success and a failure, the
    highest severity with a success is the overall maximum severity, and the lowest severity
    with a failure is the overall minimum, so "highest success <= lowest failure" only holds
    when there is a single level -- ruled out below by requiring at least 2.
    """
    n = draw(st.integers(min_value=2, max_value=4))
    severities = draw(
        st.lists(
            st.floats(min_value=0.5, max_value=20.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )
    trials = draw(st.lists(st.integers(min_value=10, max_value=40), min_size=n, max_size=n))
    successes = [draw(st.integers(min_value=1, max_value=t - 1)) for t in trials]
    return severities, successes, trials


def _from_counts(counts: tuple[list[float], list[int], list[int]]) -> Observations:
    severity, successes, trials = counts
    return Observations.from_counts(
        _AXIS,
        severity=severity,
        successes=successes,
        trials=trials,
        outcome="success",
        direction="decreasing",
    )


def _fit_fixed_trivial(obs: Observations) -> Fit:
    return fit_dose_response(obs, model="binomial", link="probit", upper=1.0, lower=0.0)


def _rows_from_counts(
    counts: tuple[list[float], list[int], list[int]],
) -> Observations:
    severity, successes, trials = counts
    row_severity: list[float] = []
    row_success: list[int] = []
    for level, n_success, n_trials in zip(severity, successes, trials, strict=True):
        row_severity.extend([level] * n_trials)
        row_success.extend([1] * n_success + [0] * (n_trials - n_success))
    return Observations.from_observations(
        _AXIS,
        severity=row_severity,
        success=row_success,
        outcome="success",
        direction="decreasing",
    )


@given(_counts_with_optional_control())
@settings(max_examples=_MAX_EXAMPLES, deadline=None)
def test_aggregated_and_disaggregated_inputs_give_identical_fits(
    counts: tuple[list[float], list[int], list[int]],
) -> None:
    aggregated = _from_counts(counts)
    disaggregated = _rows_from_counts(counts)

    fit_aggregated = _fit_fixed_trivial(aggregated)
    fit_disaggregated = _fit_fixed_trivial(disaggregated)

    assert fit_aggregated == fit_disaggregated


@given(_counts_with_optional_control(), st.data())
@settings(max_examples=_MAX_EXAMPLES, deadline=None)
def test_row_permutation_does_not_change_the_fit(
    counts: tuple[list[float], list[int], list[int]],
    data: st.DataObject,
) -> None:
    severity, successes, trials = counts
    n = len(severity)
    order = data.draw(st.permutations(range(n)))

    original = _from_counts(counts)
    permuted = _from_counts(
        (
            [severity[i] for i in order],
            [successes[i] for i in order],
            [trials[i] for i in order],
        )
    )

    fit_original = _fit_fixed_trivial(original)
    fit_permuted = _fit_fixed_trivial(permuted)

    assert fit_original == fit_permuted


@given(_non_separated_counts(), st.integers(min_value=1, max_value=200))
@settings(max_examples=_MAX_EXAMPLES, deadline=None)
def test_adding_an_all_success_control_leaves_a_fixed_u_1_fit_unchanged(
    counts: tuple[list[float], list[int], list[int]],
    control_trials: int,
) -> None:
    severity, successes, trials = counts

    without_control = _from_counts((severity, successes, trials))
    with_control = _from_counts(
        ([0.0, *severity], [control_trials, *successes], [control_trials, *trials])
    )

    fit_without = _fit_fixed_trivial(without_control)
    fit_with = _fit_fixed_trivial(with_control)

    # The control row is dropped from the u=1,l=0 GLM likelihood entirely (plan section 5.1),
    # and contributes exactly 0 to the full binomial log-likelihood (an all-success row's term
    # is lchoose(n,0) + n*log(1) == 0 identically) -- so status, params, covariance and
    # log_likelihood must all agree exactly, not just approximately.
    assert fit_with.status == fit_without.status
    if fit_without.status is Status.OK:
        assert fit_with.params == fit_without.params
        assert fit_with.covariance == fit_without.covariance
        assert fit_with.log_likelihood == fit_without.log_likelihood


@given(
    _non_separated_counts(),
    st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=_MAX_EXAMPLES, deadline=None)
def test_rescaling_severity_shifts_mu_by_log_c_and_leaves_s_unchanged(
    counts: tuple[list[float], list[int], list[int]],
    c: float,
) -> None:
    severity, successes, trials = counts
    rescaled_severity = [c * s for s in severity]

    original = _from_counts((severity, successes, trials))
    rescaled = _from_counts((rescaled_severity, successes, trials))

    fit_original = _fit_fixed_trivial(original)
    fit_rescaled = _fit_fixed_trivial(rescaled)

    assume(fit_original.status is Status.OK)
    assume(fit_rescaled.status is Status.OK)
    assert fit_original.params is not None
    assert fit_rescaled.params is not None

    assert fit_rescaled.params["mu"].value == pytest.approx(
        fit_original.params["mu"].value + math.log(c), rel=1e-6, abs=1e-9
    )
    assert fit_rescaled.params["s"].value == pytest.approx(
        fit_original.params["s"].value, rel=1e-6, abs=1e-9
    )
