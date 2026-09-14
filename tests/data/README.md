# Provenance — `zeta_matrix_counts.csv`

**Source:** `../zeta-bench/results/robustness_matrix.csv`, `badkoubeh/zeta-bench` at
`origin/main` commit `41e5a2c` (`41e5a2cd1de4806ff15757c1324efa718c7fe6a6`). The pooling and
break-point logic mirrored below is `robustness/cards.py::degradation_curve` and
`::break_point`, introduced in squash commit `435fc2793b2afdb8404099c83b0c36a71d9ffba9`
(PR #17), per `docs/decisions/0002-provenance-by-copy.md`.

## How the counts were derived

`degradation_curve` builds one curve per `(controller, disturbance_type)` pair by averaging
`success_rate` over the family's secondary nuisance axis (wind direction for `wind`, spike
probability for `sensor_noise`) at each severity level, then anchoring severity 0 on the
`nominal` row **unless** the family already tests a `0.0` level itself (`sensor_noise` does;
`wind` and `mass` do not).

This fixture pools `n_success` / `n_episodes` **counts**, not rates, per severity level:

```text
successes(level) = sum(n_success over rows at that (controller, family, severity))
trials(level)     = sum(n_episodes over rows at that (controller, family, severity))
```

Every pooled row in `robustness_matrix.csv` has `n_episodes == 100`, so summing counts and
taking `successes / trials` reproduces `degradation_curve`'s mean-of-rates exactly (an
unweighted average of equal-`n` cells equals the ratio of summed counts). This is an
assumption specific to this matrix, not a general property of count pooling, and would need
re-deriving if a future matrix had unequal `n` per cell. The zero-level anchor uses the
`nominal` row's own `(n_success, n_episodes)` for the same reason.

Derived counts were cross-checked two ways:
1. Recomputed from the raw CSV with a script that reimplements the two rules above.
2. Compared against the pooled curves and `break_point` outputs already committed in
   `../zeta-bench/results/cards/{pid,sac,ppo}.json` (`variants.*.families.*.curve` /
   `break_point` / `max_tested`), generated from the same matrix. All five series agree with
   the card JSON exactly; see `tests/unit/test_empirical.py`, where the expected break-points
   are copied in as literals (tests never read `../zeta-bench` at runtime).

## Columns

`series, axis, severity, successes, trials` — neutral names per `CLAUDE.md` hard constraint 4
and plan section 3.1. `series` is `{controller}_{axis}` (e.g. `pid_sensor_noise`); `controller`
labels (`pid`, `sac`, `ppo`) and `axis` labels (`sensor_noise`, `wind`, `mass`) are copied
verbatim from the source CSV's `controller` / `disturbance_type` columns — they are
generic physical-quantity and algorithm labels, not domain vocabulary, and the plan's own
section 3.1 table already uses them. `mass` (`ppo_mass`) keeps its sign, since the source axis is signed
(the curve runs from the heaviest negative offset through nominal to the heaviest positive
one); every other axis here is unsigned.

## The six cases vs. five series — a structural mismatch with plan section 3.1

Plan section 3.1's table lists six *cases* but they do not require six distinct data series.
"Baseline already below gate" (row 5: `98/200`, `57/200`) is not separate data — it is the
`severity == 0.0` row already present in the `sac_sensor_noise` and `ppo_sensor_noise` series
(rows 3 and 4). This fixture therefore has **five** series covering all **six** edge cases from
the table. This is a wording mismatch in the plan's table, not a numeric one: every count below
agrees with plan section 3.1's table and with the committed card JSON.

## Series → edge case

| Series | Axis | Case from plan section 3.1 |
|---|---|---|
| `pid_sensor_noise` | `sensor_noise` | Identifiable transition |
| `pid_wind` | `wind` | Right-censored, complete separation |
| `sac_sensor_noise` | `sensor_noise` | Left-censored; also: baseline already below gate |
| `ppo_sensor_noise` | `sensor_noise` | Non-monotone; also: baseline already below gate |
| `ppo_mass` | `mass` | Signed and asymmetric |

The "left-censored" / "non-monotone" labels above are the plan's names for the *data shape*
of that case, describing the eventual dose-response model's censoring classification
(`censoring.py`, plan section 5.5, Phase 5 — not yet implemented). `grid_break_point` itself
never emits `LEFT` or `OPEN_*`: on this data it reports `sac_sensor_noise` and
`ppo_sensor_noise` as `value=0.0, censoring=NONE` (the zero level itself already fails the
0.95 gate), not `LEFT`. See `tests/unit/test_empirical.py`.

