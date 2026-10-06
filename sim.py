"""
sim.py - toy simulation of Spanner's external-consistency protocol.

Implements the two timestamp rules from Section 4.1.2 of "Spanner: Google's
Globally Distributed Database" (Corbett et al., ACM TOCS 2013):

  Start       : the coordinator picks a commit timestamp s >= TT.now().latest
  Commit wait : the coordinator does not acknowledge the commit (make it
                visible) until TT.after(s) is true

and measures, for pairs of transactions (T1, T2), whether the guarantee

    T1 acknowledged before T2 starts (in true time)  =>  s1 < s2

holds. Three commit modes are compared:

  "naive"      : s = the coordinator's local clock reading, ack immediately
  "start_only" : s = TT.now().latest, ack immediately (start rule alone)
  "spanner"    : s = TT.now().latest, then commit wait, then ack (both rules)

Deliberately left out: Paxos, locks, two-phase commit, multi-key data.
Each commit is a single timestamp assignment at a single coordinator.
"""

import random
from dataclasses import dataclass

from truetime import SimClock, TrueTime

MODES = ("naive", "start_only", "spanner")


@dataclass
class Txn:
    start: float  # true time at which the commit began
    s: float      # assigned commit timestamp
    ack: float    # true time at which the commit was acknowledged / visible

    @property
    def wait(self):
        """Latency added by the commit protocol (0 unless commit wait ran)."""
        return self.ack - self.start


def commit_wait(node, clock, s):
    """Advance true time until TT.after(s) holds at this node.

    Rather than ticking in tiny steps, jump straight to the moment
    node.now().earliest passes s (exact when the node has no drift; the loop
    handles the drift case by re-checking).
    """
    for _ in range(100):
        if node.after(s):
            return
        gap = s - node.now().earliest
        clock.advance(max(gap, 0.0) + 1e-9)
    raise RuntimeError("commit wait did not converge")


def commit(node, clock, mode):
    """Run one commit at `node` under the given mode; returns a Txn."""
    start = clock.t
    if mode == "naive":
        s = node.local()
    elif mode in ("start_only", "spanner"):
        s = node.now().latest          # Start rule
    else:
        raise ValueError(f"unknown mode {mode!r}")

    if mode == "spanner":
        commit_wait(node, clock, s)    # Commit wait rule

    return Txn(start=start, s=s, ack=clock.t)


def run_pair(clock, node_a, node_b, mode, gap):
    """T1 commits at node A and is acknowledged; `gap` ms later T2 starts and
    commits at node B."""
    t1 = commit(node_a, clock, mode)
    clock.advance(gap)
    t2 = commit(node_b, clock, mode)
    return t1, t2


def externally_consistent(t1, t2):
    """The checker. Only pairs where T1 was acknowledged before T2 started
    constrain the ordering; for those, we need s1 < s2."""
    if t1.ack < t2.start:
        return t1.s < t2.s
    return True


def run_trials(n, eps, mode, violation_factor=1.0, gap_max=20.0, seed=0):
    """Run n independent (T1, T2) pairs and report violations and latency.

    Each trial draws two fresh nodes whose clock offsets are uniform in
    [-k*eps, +k*eps] with k = violation_factor, while both advertise eps.
        k <= 1 : advertised eps is a true bound (TrueTime assumption holds)
        k  > 1 : real clock error exceeds the advertised bound (assumption broken)
    The real-time gap between T1's ack and T2's start is uniform in
    (0, gap_max] ms.
    """
    rng = random.Random(seed)
    bound = violation_factor * eps
    violations = 0
    total_wait = 0.0
    for _ in range(n):
        clock = SimClock(1000.0)
        a = TrueTime(clock, eps, offset=rng.uniform(-bound, bound))
        b = TrueTime(clock, eps, offset=rng.uniform(-bound, bound))
        gap = rng.uniform(1e-6, gap_max)
        t1, t2 = run_pair(clock, a, b, mode, gap)
        if not externally_consistent(t1, t2):
            violations += 1
        total_wait += t1.wait + t2.wait
    return {
        "mode": mode,
        "eps": eps,
        "violation_factor": violation_factor,
        "n": n,
        "violations": violations,
        "violation_rate": violations / n,
        "mean_commit_wait": total_wait / (2 * n),
    }


if __name__ == "__main__":
    print("eps = 4 ms, 20000 trials, healthy clocks (k = 1)")
    for mode in MODES:
        r = run_trials(20000, eps=4.0, mode=mode, seed=1)
        print(f"  {mode:11s} violations={r['violations']:5d} "
              f"({r['violation_rate']:.2%})  mean wait={r['mean_commit_wait']:.2f} ms")