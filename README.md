# marginkit
Robustness margins with confidence intervals, via dose-response threshold estimation. Model-agnostic — no GPU, no ML framework required

> **Status: alpha, `0.1.0a2`.** This release contains the grid break-point rule described below,
> plus the result objects, JSON score-card schema and test fakes that later estimation will
> return. Dose-response fits, thresholds with confidence intervals, and ratios of thresholds are
> **not available yet**: nothing produces a `Fit`, `Threshold` or `Ratio` except
> `marginkit.testing`. The public API may still change before `0.1.0`.

## What it does today

`grid_break_point` finds the smallest tested severity at which observed performance falls
strictly below a criterion. It reports an **observed grid statistic, not an estimated
threshold**. The reported value is always one of the severities you tested. It is never
interpolated, and it has no confidence interval.

## Install

Requires Python 3.11 or later. marginkit is not on PyPI yet, so install it from the release tag:

```bash
pip install "marginkit @ git+https://github.com/badkoubeh/marginkit@v0.1.0a2"
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

## Results and JSON

Every result is a frozen dataclass carrying a `schema_version` and a `provenance` mapping.
`provenance` records where the inputs came from; marginkit stores it and never interprets it.

- `GridBreakPoint` is what `grid_break_point` returns today.
- `Fit`, `Threshold` and `Ratio` are the result types later estimation will return. They check
  their own consistency when constructed. For example, a failed fit cannot carry parameters, and
  a censored threshold cannot carry a point estimate.

Results are collected in a `Scorecard` and written to JSON with `marginkit.report`:

```python
import json

from marginkit import Scorecard, grid_break_point
from marginkit.report import from_dict, load_schema, to_dict

held = grid_break_point([0.0, 1.0, 2.0], [1.0, 0.99, 0.97], criterion=0.95)
card = Scorecard(results=(held,), provenance={"run": "example"})

text = json.dumps(to_dict(card), allow_nan=False)
assert from_dict(json.loads(text)) == card
assert load_schema()["$schema"] == "https://json-schema.org/draft/2020-12/schema"
```

The JSON follows `schema/scorecard-v1.json`, a JSON Schema shipped inside the package. Version 1
covers binary outcomes only, and reading is strict: a card with fields this marginkit does not
know is rejected, not silently trimmed. To read a stored card, use a marginkit at least as new as
the one that wrote it.

For your own tests, `marginkit.testing` provides `fake_fit`, `fake_threshold` and `fake_ratio`.
They return schema-valid results in every status and censoring state, and each is labelled as a
fake rather than an estimate.

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
