# Changelog

All notable changes to marginkit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html). While the version is below 1.0 a
minor bump may contain breaking changes; `docs/decisions/0003-consumer-version-policy.md` is
what consumers pin against.

Every entry that adds, renames, removes, or changes the behaviour of a public symbol must also
satisfy the public-API change checklist in `docs/IMPLEMENTATION_PLAN.md` Appendix B.

## [Unreleased]

## [0.1.0a1] — 2026-09-13

To be tagged as `v0.1.0a1` on GitHub once this release's PR is merged. Not uploaded to PyPI: package naming and publication (D3) is
still an open owner decision.

### Added

- `marginkit.grid_break_point(severity, performance, *, criterion, signed=False)`, returning a
  frozen `GridBreakPoint(value, max_tested, censoring)`: the smallest tested severity magnitude
  whose performance is strictly below `criterion`, or `value=None` with `Censoring.RIGHT` when
  no tested level fails. It reports an observed grid statistic, not an estimate of a threshold.
  The rule's conventions are copied from zeta-bench's `robustness/cards.py::break_point`
  (`badkoubeh/zeta-bench@435fc27`); see `docs/PROVENANCE.md`.
- `marginkit.Censoring`, with all five members specified for the v0.1 contract:
  `NONE`, `RIGHT`, `LEFT`, `OPEN_UPPER`, `OPEN_LOWER`. `grid_break_point` uses only `NONE` and
  `RIGHT`. The rest are declared now so that the model-based thresholds in later phases do not
  add enum members a consumer must handle.
- `tests/data/zeta_matrix_counts.csv`: pooled per-level counts from zeta-bench's committed
  matrix, covering the edge cases the package must handle, with a provenance note.
- `docs/PROVENANCE.md`, committed (the rest of `docs/` stays private).

### Differences from the zeta-bench source

- Empty input, mismatched lengths, non-finite values, and negative severities without
  `signed=True` raise `ValueError`. zeta-bench returned `(None, None)` for an empty curve and
  treated a NaN rate as passing.

### Notes

- First release with public API. `GridBreakPoint` also carries `schema_version` (default `"1"`)
  and an opaque `provenance` mapping (default empty), which marginkit stores and never
  interprets. Set it with `dataclasses.replace`. JSON serialisation arrives with `report.py`
  in Phase 3.
- `GridBreakPoint.censoring` is a point-estimate label for the grid: `RIGHT` means no tested
  level fell below the criterion. It carries no exact one-sided test and no monotonicity
  assumption, so it is not the model-based classification that later thresholds will report.
- Version ranges: decision 0003 specifies `marginkit>=0.X,<0.(X+1)`. Under PEP 440 the
  pre-release `0.1.0a1` sorts below `0.1`, so `>=0.1,<0.2` excludes it. An owner amendment to
  0003 is pending. Until marginkit is on PyPI, the only consumer depends on the git tag, so
  nothing is affected yet.

## [0.1.0.dev0] — Phase 1 bootstrap, untagged

### Added

- Packaging and tooling skeleton: setuptools with an `src/` layout, an SPDX `license` field,
  `py.typed`, `requires-python >= 3.11`, and the runtime dependency set `numpy`, `scipy`,
  `statsmodels`.
- `ruff` (line length 100), `mypy --strict` over `src/`, and `pytest` with a 90% branch-coverage
  gate, all wired into pre-commit and GitHub Actions.
- A CI matrix covering Python 3.11, 3.12 and 3.13 against current dependencies, plus a
  dependency-floor job on Python 3.11 (`ci/constraints-min.txt`), so the declared floors are
  tested at the floor rather than merely declared.
- A packaging job that asserts `py.typed` is present inside the built wheel. A missing marker
  fails silently and disables type checking for every consumer.
- A test asserting that importing `marginkit` pulls in no GPU, ML-framework, or plotting module.
- Owner decision records 0001 through 0004, covering parallel milestone scheduling, the
  provenance method, the consumer version policy, and models with non-trivial asymptotes.

### Notes

- No public API yet. The contract is specified in `docs/IMPLEMENTATION_PLAN.md` sections 4.1 and
  4.2 and is frozen in Phase 3, under owner review.
