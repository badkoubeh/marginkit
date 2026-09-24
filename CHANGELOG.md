# Changelog

All notable changes to marginkit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html). While the version is below 1.0 a
minor bump may contain breaking changes; `docs/decisions/0003-consumer-version-policy.md` is
what consumers pin against.

Every entry that adds, renames, removes, or changes the behaviour of a public symbol must also
satisfy the public-API change checklist in `docs/IMPLEMENTATION_PLAN.md` Appendix B.

## [Unreleased]

Phases 4 and 5, to be tagged `v0.1.0a3`. Additive; upgrading from 0.1.0a2 needs no consumer
change. The two phases share one version because `v0.1.0a3` was never tagged for Phase 4 on its
own -- Phase 4 merged with `__version__` still at `0.1.0a2`, so retro-tagging that commit would
ship a package reporting the wrong version.

### Phase 4 -- dose-response fitting

### Added
- `fit_dose_response(obs, *, model, link, upper, lower) -> Fit`. All four keywords are required,
  with no defaults: `model="binomial"`; `link` one of `"probit"`, `"logit"`, `"cloglog"`;
  `upper`/`lower` a float or `"estimate"`. Asymptotes fixed at 1 and 0 fit with statsmodels
  `GLM`; anything else with `GenericLikelihoodModel` (`decisions/0004`). A failed fit returns a
  `Fit` whose `status` says so (`SEPARATION`, `NOT_CONVERGED`, `CONTROL_INCOMPATIBLE`), with
  `params`, `covariance` and `log_likelihood` set to `None` and the reason in `warnings`.
  `direction="increasing"` raises `ValueError`. `Fit.cluster_ids` is copied from `obs`.
- `Fit.predict(severity, *, level=0.95) -> Prediction`, with pointwise delta-method bands.
  Raises `ValueError` unless `status` is `OK`.
- `Prediction`: frozen, keyword-only, compared by identity (`eq=False`); read-only numpy array
  fields `severity`, `estimate`, `lo`, `hi` and a float `level`. Not serialisable:
  `report.to_dict` and `Scorecard` reject it.
- R `drc`/`MASS` reference fixtures and their generator in `tools/drc_reference/`.
- Decisions `0005` (no interior maximum → `NOT_CONVERGED`), `0006` (separation from the exact
  overlap check, amending plan §5.2) and `0007` (observed-information covariance).

### Changed
- `Covariance` positive-definiteness is now checked on the correlation matrix: every variance
  `> 0` and minimum correlation eigenvalue `> 1e-12`, replacing minimum eigenvalue
  `> 1e-12·max(1, max|entry|)`. A fit's status no longer depends on severity units. This only
  loosens the rule: every matrix 0.1.0a2 accepted is still accepted. Stored cards: a `Fit`
  written by this version may be rejected by a 0.1.0a2 reader; read cards with a marginkit at
  least as new as the writer.

### Unchanged
- JSON schema v1 and every existing field and signature.

### Notice (now in effect, as of Phase 5)
- Exporting `threshold()` has made the attribute `marginkit.threshold` the function, not the
  module. `import marginkit.threshold as m; m.Threshold` no longer works. Use
  `from marginkit import Threshold`; `from marginkit.threshold import Threshold` still resolves
  through `sys.modules` but is not API.

### Phase 5 -- thresholds, intervals, censoring

#### Added
- `threshold(fit, *, definition, interval_method, level, dependence=None) -> Threshold`. Solves
  for the severity at which the fitted curve crosses a target performance, for all three
  definitions (`absolute`, `baseline_fraction`, `relative`); `definition` has no default,
  pending D5. `interval_method` is `"profile"` (primary) or `"delta"`, and is a *request*: on
  any censored or failed path the result records `"exact_bound"`. Omitting `dependence` on
  clustered input raises (R2).
- `Threshold.baseline: BaselineRate | None` and `Threshold.grid: GridBreakPoint | None`, both
  defaulting to `None`. They carry what plan section 5.5 says a `FAILS_AT_BASELINE` and a
  `SEPARATION`/`NOT_CONVERGED` result must report, which previously had nowhere to live
  (`decisions/0010`). Appended fields: code upgrading from 0.1.0a2 is unaffected, but a stored
  card carrying them must be read by a marginkit at least as new as the writer.
- `BaselineRate`: the control cell's rate with its exact interval, labelled
  `per_cell_clopper_pearson`. Serialisable, as a `Threshold` field.
- `per_cell_clopper_pearson(cells, *, level=0.95) -> ExactRates`. `ExactRates` is deliberately
  **not** serialisable and has no schema entry, which is what enforces plan section 5.4's rule
  that per-cell exact rates never attach to a threshold.
- Internal modules `marginkit.censoring` (section 5.5's rules and the exact one-sided bounds)
  and `marginkit.intervals` (profile and delta). Neither import path is API.
- Decisions `0008` (`baseline_fraction` reachability, the fallback `u`, and `FAILS_AT_BASELINE`
  before `UNREACHABLE`), `0009` (each side of a two-sided exact bracket at `(1 + level)/2`),
  `0010` (the two appended fields), `0011` (exact bounds contradicting monotonicity report no
  bounds), `0012` (section 5.5's `RIGHT`/`LEFT` conditions outrank a converged fit), `0013` (an
  interval unbounded on both sides reports the estimate with no bounds) and `0014` (a crossing at
  or below zero severity on a linear axis is `UNREACHABLE`).

#### Changed
- **`Threshold`'s `(status=OK, censoring=NONE)` invariant is loosened.** `value` is still
  required, but `lo` and `hi` may now both be `None` (they must be both set or both `None`). A
  converged fit on a design too coarse to constrain the parameter has a profile that crosses the
  chi-square target on neither side, and v1 has no `Censoring` member for "open on both sides";
  the estimate is reported, the bounds are not, and `warnings` names the search limits that were
  reached (`decisions/0013`). Safe for code that *constructs* a `Threshold`. **Code that reads
  `Threshold.lo`/`.hi` must now handle `None` on the `OK` path, not only on the censored ones.**
- `threshold()` returns `Status.UNREACHABLE` with `censoring=NONE` and no numbers when the
  closed-form solve lands at or below zero severity on a linear axis, rather than raising from
  `Threshold`'s non-negativity rule. `UNREACHABLE` now has two causes and `warnings` tells them
  apart (`decisions/0014`). Only linear axes can reach it.
- `Threshold`'s docstring no longer claims a `SEPARATION`/`NOT_CONVERGED` bracket has joint
  coverage `2 * level - 1`. Each side is now computed at `(1 + level)/2`, so joint coverage is
  at least `level` and `Threshold.level` means the same thing on every path (`decisions/0009`).
  Behavioural for brackets, which are wider than the superseded wording implied; one-sided
  `RIGHT`/`LEFT` bounds are unchanged at `level`.
- The default `pytest` run excludes the `slow` marker, and a separate CI job runs plan section
  6.3's coverage simulations once rather than on each of four matrix legs.

## [0.1.0a2] — 2026-09-14

The v1 contract: vocabulary, result objects, the JSON score-card schema, and test fakes, published
before any estimation exists so that consumers can build against them. To be tagged `v0.1.0a2`
once the owner has approved the public API surface and this release's PR is merged. Not uploaded
to PyPI: D3 is still open.

### Added

- Vocabulary in `marginkit`:
  - `Axis(name, unit, scale, citation)`, with `scale` either `"log"` or `"linear"`.
  - `Observations.from_counts(...)` and `Observations.from_observations(..., cluster=...)`.
    `outcome` and `direction` are required. Both forms pool into the same `cells()`.
  - `Definition.absolute(a)`, `.baseline_fraction(p)` and `.relative(p)`.
  - `Cell`, plus the `Status` and `IntervalShape` enums. Their values equal their member names,
    as in `Censoring`.
- Result objects `Parameter`, `Covariance`, `Fit`, `Threshold` and `Ratio`. These are frozen,
  keyword-only dataclasses that check their invariants when constructed:
  - A failed fit carries no parameters, covariance or log-likelihood.
  - A threshold follows the censoring rules: a censored or failed threshold never carries a
    point estimate, and its status must agree with its fit's status.
  - A ratio requires the same axis, unit and definition on both sides. With
    `dependence="independent"`, it refuses thresholds whose fits share cluster ids.
- Dependence is recorded in results: `Fit.cluster_ids` holds the fit's cluster ids, and
  `Threshold.dependence` is required. A stored result therefore shows when independence was
  assumed.
- `marginkit.types.JSONValue`, the type of the values allowed in `provenance`.
- `Scorecard`, and `marginkit.report` with `SCHEMA_VERSION`, `to_dict`, `from_dict` and
  `load_schema`. The schema is `schema/scorecard-v1.json` (JSON Schema draft 2020-12), shipped in
  the wheel. `GridBreakPoint` serialises under the same schema and may appear in a `Scorecard`.
- `marginkit.testing.fake_fit`, `fake_threshold` and `fake_ratio`: schema-valid results for
  consumers' own tests. Each is labelled as a fake and is not an estimate.

### Notes

- **No estimation yet.** Nothing in this release produces a `Fit`, `Threshold` or `Ratio` except
  `marginkit.testing`. `fit_dose_response`, `threshold` and `ratio_interval` arrive in later
  releases.
- **Schema v1 is binomial-only and strict.** `from_dict` rejects unknown fields rather than
  dropping them, so reading a stored card needs a marginkit at least as new as the one that wrote
  it. A new result family or enum value (for example continuous fits or paired ratios) will mean
  schema version `"2"`.
- **Binomial results accept only `direction="decreasing"`**, until owner decision D5 defines the
  increasing case. `Observations` accepts both directions.
- **A failed or censored `Ratio` carries no shape, estimate or bounds**, until one-sided ratio
  bounds are specified.
- `grid_break_point`, the `GridBreakPoint` fields and `Censoring` are unchanged.

## [0.1.0a1] — 2026-09-13

Tagged `v0.1.0a1` on GitHub at `cdd0410`. Not uploaded to PyPI: package naming and publication
(D3) is still an open owner decision.

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
