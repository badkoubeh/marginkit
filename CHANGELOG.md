# Changelog

All notable changes to marginkit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html). While the version is below 1.0 a
minor bump may contain breaking changes; `docs/decisions/0003-consumer-version-policy.md` is
what consumers pin against.

Every entry that adds, renames, removes, or changes the behaviour of a public symbol must also
satisfy the public-API change checklist in `docs/IMPLEMENTATION_PLAN.md` Appendix B.

## [Unreleased]

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
