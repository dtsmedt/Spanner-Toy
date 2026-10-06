# spanner-toy: TrueTime and commit wait in simulation

A small simulation of the core mechanism from *Spanner: Google's Globally
Distributed Database* (Corbett et al., ACM TOCS 2013): **TrueTime** (a clock API
that returns an uncertainty interval) and **commit wait** (delay acknowledging a
commit until its timestamp is definitely in the past). The simulation checks the
paper's headline guarantee, *external consistency*, and measures what it costs.

**What it shows.** With clocks skewed within a bound ε, timestamping transactions
with local clocks (or with `TT.now().latest` alone) violates external consistency
in up to 17% of transaction pairs at ε = 10 ms. Adding commit wait eliminates
every violation, at a latency cost of exactly 2ε. If the real clock error exceeds
the advertised ε, violations come back, so correctness depends on the bound being
*valid*, not *small*.

## Files

| File | Purpose |
|---|---|
| `truetime.py` | `SimClock` (shared true time) and `TrueTime` (per-node `now()`, `after()`, `before()`), plus a self-test |
| `sim.py` | The three commit modes, the (T1, T2) workload, the external-consistency checker, and `run_trials` |
| `experiments.py` | Runs experiments A, B and C; writes plots and `results.csv` |
| `requirements.txt` | `matplotlib` (plotting only; the simulation uses the standard library) |
| `results/` | Generated plots and the raw numbers behind them |

## Running it

```
pip install -r requirements.txt
python truetime.py        # self-test of the TrueTime class
python sim.py             # quick three-mode comparison at eps = 4 ms
python experiments.py     # full experiments -> results/
```

Everything is seeded (`SEED = 7` in `experiments.py`) and runs on simulated
time, so results are deterministic and the full run takes a few seconds.

## Paper concepts mapped to code

| Paper | Code |
|---|---|
| TTinterval `[earliest, latest]` (Sec. 3, Table I) | `TTinterval`, returned by `TrueTime.now()` |
| `TT.after(t)`, `TT.before(t)` | `TrueTime.after`, `TrueTime.before` |
| Uncertainty bound ε | the `eps` argument; each node's clock offset is drawn within it |
| Start rule: `s >= TT.now().latest` (Sec. 4.1.2) | `commit()` in modes `"start_only"` and `"spanner"` |
| Commit wait: hold until `TT.after(s)` (Sec. 4.1.2) | `commit_wait()` in `sim.py` |
| External consistency: T1 commits before T2 starts implies `s1 < s2` | `externally_consistent()` |
| ε must be a true bound for correctness (Sec. 3, 5.3) | `violation_factor` (k) in `run_trials` and experiment C |

## How the experiment works

Each trial draws two fresh nodes with clock offsets uniform in `[-k·ε, +k·ε]`
(k = 1 means ε is a true bound). T1 commits at node A and is acknowledged. A
random real-time gap in (0, 20] ms later, T2 starts and commits at node B. The
checker verifies `s1 < s2` for every pair where T1's acknowledgment precedes T2's
start in true time. Three commit modes are compared:

- **naive**: `s` is the node's local clock reading; acknowledge immediately.
- **start_only**: `s = TT.now().latest`; acknowledge immediately.
- **spanner**: `s = TT.now().latest`, then wait until `TT.after(s)`, then acknowledge.

All three modes see identical offsets and gaps in each experiment (same seed),
so differences between them come only from the protocol.

## Results

Each point uses 20,000 trials. Raw numbers are in `results/results.csv`.

### A. Correctness: `results/violations_vs_eps.png`

| ε (ms) | naive | start only | spanner |
|---|---|---|---|
| 0 | 0.00% | 0.00% | 0.00% |
| 2 | 3.40% | 3.40% | 0.00% |
| 4 | 6.80% | 6.80% | 0.00% |
| 10 | 17.01% | 17.01% | 0.00% |

Only the full protocol preserves external consistency. The start-only curve is
**identical** to the naive one, not just close. This is expected: `TT.now().latest`
is the local clock plus ε, so every timestamp shifts by the same constant and the
relative order of T1 and T2 is unchanged. Choosing a timestamp at or above the
current time is not enough; commit wait is what makes it provably already past
when clients see the result.

*Sanity check.* For naive timestamps, a violation occurs when `offset_A - offset_B`
is at least the gap. With uniform offsets this gives an analytic rate of about
6.7% at ε = 4 ms and 16.7% at ε = 10 ms with this gap distribution, against 6.80%
and 17.01% measured.

### B. Cost: `results/commit_wait_vs_eps.png`

Mean commit wait in spanner mode is exactly 2ε (2, 4, 8 and 20 ms at ε = 1, 2, 4
and 10), matching the paper's analysis. A commit at `TT.now().latest = local + ε`
must wait until `TT.now().earliest = local - ε` passes that point, a span of 2ε,
independent of the node's actual offset. The other two modes add no latency, which
is why they are unsafe.

### C. Broken bound: `results/broken_bound.png`

With advertised ε fixed at 4 ms and real clock error up to k·ε:

| k | 1.0 | 1.25 | 1.5 | 2 | 3 | 4 |
|---|---|---|---|---|---|---|
| spanner violations | 0.00% | 0.08% | 0.40% | 1.62% | 5.86% | 11.41% |

Commit wait is still performed (still 8 ms), but it no longer helps once a node's
interval can miss true time. Violations require `offset_A - offset_B >= 2ε + gap`,
which is impossible while every offset is within ε, hence exactly zero up to k = 1
and a rapid rise afterward. This mirrors the paper's point that a large ε only
costs performance, while an *incorrect* ε costs correctness.

## What is deliberately left out

This is a toy of one mechanism, not a database. Not implemented:

- Paxos replication, leader leases, and lease disjointness (Sec. 4.1.1, 4.2.5)
- Locking, two-phase commit, and multi-key or multi-group transactions
- Safe time, snapshot reads, and schema-change transactions (Sec. 4.1.3 to 4.2.3)
- GPS and atomic time masters, Marzullo-style outlier rejection, and the polling
  sawtooth. Each node's clock offset is a fixed random draw within ε.
- Clock drift between syncs. `TrueTime` supports a `drift` parameter, but the
  experiments use `drift = 0`, so uncertainty is constant.
- Real networks. Time advances only through explicit `advance()` calls, and
  messaging delays are not modeled.

## Credits

- Paper: J. C. Corbett et al., "Spanner: Google's Globally Distributed Database,"
  *ACM Transactions on Computer Systems* 31(3), Article 8, 2013.
- Plotting uses [matplotlib](https://matplotlib.org/).
