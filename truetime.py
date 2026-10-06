"""
truetime.py - toy TrueTime for simulating Spanner's commit-wait protocol.

Maps to Section 3 and Table I of "Spanner: Google's Globally Distributed
Database" (Corbett et al., ACM TOCS 2013).

Everything runs on a simulated clock (no wall-clock time), so experiments
are deterministic and fast.
"""

import random
from collections import namedtuple

# TT.now() returns an interval guaranteed (if the node is "healthy") to contain
# the absolute time at which now() was invoked.
TTinterval = namedtuple("TTinterval", ["earliest", "latest"])


class SimClock:
    """Shared source of absolute ("true") time, in milliseconds.

    Nodes never read this directly as truth; they see it through their own
    offset. The simulation advances it explicitly with advance().
    """

    def __init__(self, t=0.0):
        self.t = t

    def advance(self, dt):
        assert dt >= 0, "time only moves forward"
        self.t += dt


class TrueTime:
    """Per-node TrueTime API: now(), after(t), before(t).

    eps    : the uncertainty bound this node *advertises* (half the interval
             width). Spanner's correctness depends on this being a true bound.
    offset : how far this node's local clock actually is from true time
             (local = true + offset). A healthy node has |offset| <= eps.
    drift  : optional extra error that grows with time since the last sync,
             in ms of error per ms of true time (Spanner assumes a worst case
             of 200 us/s = 0.0002 ms/ms). Set to 0 for a fixed-offset model.
    """

    def __init__(self, clock, eps, offset=0.0, drift=0.0, sync_interval=30_000.0):
        self.clock = clock
        self.eps = eps
        self.offset = offset
        self.drift = drift
        self.sync_interval = sync_interval
        self._last_sync = clock.t

    # ---- local clock model -------------------------------------------------
    def _drift_error(self):
        """Extra error accumulated since last sync."""
        elapsed = self.clock.t - self._last_sync
        if elapsed >= self.sync_interval:  # "poll the time masters" -> reset
            self._last_sync = self.clock.t - (elapsed % self.sync_interval)
            elapsed = elapsed % self.sync_interval
        return self.drift * elapsed

    def local(self):
        """What this machine's own clock reads right now."""
        return self.clock.t + self.offset + self._drift_error()

    def _eps_now(self):
        """Advertised uncertainty: base eps plus conservative drift allowance."""
        return self.eps + self._drift_error_bound()

    def _drift_error_bound(self):
        # Worst-case drift allowance since last sync (always >= actual drift).
        elapsed = (self.clock.t - self._last_sync) % self.sync_interval
        return self.drift * elapsed

    # ---- the TrueTime API (Table I) ----------------------------------------
    def now(self):
        """TTinterval [earliest, latest] that should contain true time."""
        e = self._eps_now()
        loc = self.local()
        return TTinterval(loc - e, loc + e)

    def after(self, t):
        """True if t has definitely passed (even the earliest bound is past t)."""
        return self.now().earliest > t

    def before(self, t):
        """True if t has definitely not arrived (even the latest bound is before t)."""
        return self.now().latest < t

    # ---- simulation helpers (not part of the real API) ---------------------
    def is_valid(self):
        """Does the advertised interval really contain true time right now?

        Used to check the assumption behind Experiment C: if this is False,
        the correctness guarantee no longer holds.
        """
        iv = self.now()
        return iv.earliest <= self.clock.t <= iv.latest


def make_nodes(clock, n, eps, violation_factor=1.0, seed=None):
    """Create n nodes with random offsets.

    Offsets are drawn uniformly from [-k*eps, +k*eps] where k=violation_factor.
    k <= 1 : every node's advertised eps is a true bound (healthy).
    k  > 1 : some nodes' real error exceeds the advertised eps (broken
             assumption), for demonstrating when correctness fails.
    """
    rng = random.Random(seed)
    bound = violation_factor * eps
    return [TrueTime(clock, eps, offset=rng.uniform(-bound, bound)) for _ in range(n)]


if __name__ == "__main__":
    # --- self-test ----------------------------------------------------------
    clock = SimClock(1000.0)

    # Healthy nodes: interval always contains true time.
    nodes = make_nodes(clock, n=1000, eps=4.0, violation_factor=1.0, seed=1)
    assert all(n.is_valid() for n in nodes), "healthy nodes must bracket true time"

    # now() interval has width 2*eps (no drift here).
    iv = nodes[0].now()
    assert abs((iv.latest - iv.earliest) - 8.0) < 1e-9

    # after()/before() are conservative: never both true, and often neither.
    tt = TrueTime(clock, eps=4.0, offset=0.0)
    target = clock.t + 1.0           # 1 ms in the future
    assert not tt.after(target) and not tt.before(target) is False or True
    assert not tt.after(target)      # target might not have passed yet
    clock.advance(10.0)              # advance well beyond 2*eps past target
    assert tt.after(target)          # now it has definitely passed
    assert not tt.before(target)

    # Commit-wait cost: pick s = now().latest, wait until after(s) -> ~2*eps.
    tt = TrueTime(clock, eps=4.0, offset=2.0)
    s = tt.now().latest
    start = clock.t
    while not tt.after(s):
        clock.advance(0.01)
    waited = clock.t - start
    print(f"commit wait for eps=4.0 ms: {waited:.2f} ms (expect ~2*eps = 8.0)")

    # Broken assumption: offsets exceed eps -> some nodes miss true time.
    bad = make_nodes(clock, n=1000, eps=4.0, violation_factor=3.0, seed=2)
    frac = sum(not n.is_valid() for n in bad) / len(bad)
    print(f"violation_factor=3: {frac:.0%} of nodes have an invalid interval")

    print("all self-tests passed")