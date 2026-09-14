# marginkit
Robustness margins with confidence intervals, via dose-response threshold estimation. Model-agnostic — no GPU, no ML framework required

> **Status: alpha, `0.1.0a1`.** This release contains only the grid break-point rule described
> below. Dose-response fits, thresholds with confidence intervals, and ratios of thresholds are
> planned for later 0.1 pre-releases and are **not available yet**. The public API may still
> change before `0.1.0`.

## What it does today

`grid_break_point` finds the smallest tested severity at which observed performance falls
strictly below a criterion. It reports an **observed grid statistic, not an estimated
threshold**. The reported value is always one of the severities you tested. It is never
interpolated, and it has no confidence interval.

## Install

Requires Python 3.11 or later. marginkit is not on PyPI yet, so install it from the release tag:

```bash
pip install "marginkit @ git+https://github.com/badkoubeh/marginkit@v0.1.0a1"
```

Runtime dependencies are `numpy`, `scipy`, and `statsmodels`, with loose minimum versions.

## Example

```python
from marginkit import Censoring, grid_break_point

severity = [0.0, 0.5, 1.0, 2.0, 4.0]
performance = [1.0, 0.98, 0.96, 0.91, 0.40]  # e.g. success rate at each level

result = grid_break_point(severity, performance, criterion=0.95)
assert result.value == 2.0  # first tested level strictly below 0.95
assert result.max_tested == 4.0
assert result.censoring is Censoring.NONE
```

When no tested level fails, there is no value. The result is right-censored and records how far
testing went, so it reads as "held up to 2.0", never as "cannot fail":

```python
from marginkit import Censoring, grid_break_point

held = grid_break_point([0.0, 1.0, 2.0], [1.0, 0.99, 0.97], criterion=0.95)
assert held.value is None
assert held.max_tested == 2.0
assert held.censoring is Censoring.RIGHT
```

On a signed axis, pass `signed=True`. The rule then breaks on magnitude, on whichever side fails
first:

```python
from marginkit import grid_break_point

signed = grid_break_point(
    [-0.2, -0.1, 0.0, 0.1, 0.2],
    [0.05, 0.77, 0.99, 0.33, 0.0],
    criterion=0.95,
    signed=True,
)
assert signed.value == 0.1
assert signed.max_tested == 0.2
```

Some points about the rule:

- A level sitting exactly on the criterion passes. Only `performance < criterion` fails.
- Monotonicity is neither assumed nor checked, and nothing is pooled or fitted.
- Invalid input raises `ValueError` rather than returning a placeholder. That covers empty or
  mismatched arrays, non-finite values, and negative severities without `signed=True`.

## Results

`GridBreakPoint` is a frozen dataclass: `value`, `max_tested`, `censoring`, `schema_version`
(currently `"1"`), and `provenance`. `provenance` is an optional mapping you can attach with
`dataclasses.replace` to record where the inputs came from. marginkit stores it and never
interprets it. `Censoring` members serialise as their uppercase names, for example `"RIGHT"`.
`dataclasses.asdict` works today, and versioned JSON helpers are planned.

## Provenance

marginkit's break-point and censoring conventions come from
[zeta-bench](https://github.com/badkoubeh/zeta-bench) (`robustness/cards.py::break_point`). Its
dose-response estimation is new. See [`docs/PROVENANCE.md`](docs/PROVENANCE.md) for what was
carried over and what deliberately differs.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
mypy
pytest            # enforces 90% branch coverage
```

CI runs the tests on Python 3.11, 3.12, and 3.13 against current dependencies. It also runs them
on Python 3.11 against the oldest supported versions, pinned in `ci/constraints-min.txt`.
Changes are recorded in [`CHANGELOG.md`](CHANGELOG.md).

## License

Apache-2.0. See [`LICENSE`](LICENSE).
