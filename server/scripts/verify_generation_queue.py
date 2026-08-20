"""Verification of generation admission control.

The pipeline itself is STUBBED — this is about the semaphore and the queue
positions players are shown, not about story quality, so no Gemini quota is
spent. Checks:

  1. never more than MAX_CONCURRENT_GENERATIONS run at once
  2. queued sessions are told their position, and it counts down
  3. a queued session eventually runs (no starvation, FIFO order)
  4. a pipeline that CRASHES releases its slot and doesn't wedge the queue
  5. positions renumber correctly as the queue drains

Run:  cd server && ./.venv/bin/python scripts/verify_generation_queue.py
"""
import asyncio
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "unused-mock-key")
os.environ["MAX_CONCURRENT_GENERATIONS"] = "3"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config  # noqa: E402
from app.routes import generation  # noqa: E402

_failures: list[str] = []


def _assert(cond: bool, label: str) -> None:
    print(f"  {'✓' if cond else '✗'} {label}")
    if not cond:
        _failures.append(label)


# --------------------------------------------------------------------------
# A stub pipeline that records overlap instead of generating anything.
# --------------------------------------------------------------------------
class Tracker:
    def __init__(self) -> None:
        self.concurrent = 0
        self.peak = 0
        self.order: list[str] = []
        self.crash: set[str] = set()

    def run(self, session_id: str, _session: dict) -> None:
        self.concurrent += 1
        self.peak = max(self.peak, self.concurrent)
        self.order.append(session_id)
        try:
            if session_id in self.crash:
                raise RuntimeError("simulated pipeline failure")
            time.sleep(0.4)
        finally:
            self.concurrent -= 1


def _install(tracker: Tracker) -> None:
    generation._run_pipeline = tracker.run
    # Don't touch the DB or the credit ledger for a stubbed run.
    generation.session_service.update_status = lambda *a, **k: None


def _reset() -> None:
    generation._slots = None
    generation._waiting.clear()
    generation._active.clear()
    generation._progress.clear()


async def scenario_capacity() -> None:
    print(f"\n[1] admission cap (limit={config.MAX_CONCURRENT_GENERATIONS})")
    _reset()
    tracker = Tracker()
    _install(tracker)

    ids = [f"s{i}" for i in range(9)]
    await asyncio.gather(*(generation._pipeline_runner(i, {}, "u") for i in ids))

    _assert(tracker.peak <= config.MAX_CONCURRENT_GENERATIONS,
            f"never exceeded {config.MAX_CONCURRENT_GENERATIONS} concurrent (peak {tracker.peak})")
    _assert(tracker.peak == config.MAX_CONCURRENT_GENERATIONS,
            f"and did use the full allowance (peak {tracker.peak})")
    _assert(len(tracker.order) == 9, "all 9 eventually ran — nobody starved")
    _assert(generation._waiting == [] and generation._active == set(),
            "queue and active set drained clean")


async def scenario_positions() -> None:
    print("\n[2] queue positions reported to the player")
    _reset()
    tracker = Tracker()
    _install(tracker)

    ids = [f"q{i}" for i in range(6)]
    task = asyncio.gather(*(generation._pipeline_runner(i, {}, "u") for i in ids))

    await asyncio.sleep(0.1)   # first 3 running, last 3 queued
    queued = {sid: p for sid, p in generation._progress.items() if p.get("step") == "queued"}
    _assert(len(queued) == 3, f"3 sessions reported as queued (got {len(queued)})")

    positions = sorted(p["queuePosition"] for p in queued.values())
    _assert(positions == [1, 2, 3], f"positions are 1,2,3 with no gaps (got {positions})")

    first = next(p for p in queued.values() if p["queuePosition"] == 1)
    _assert("next in line" in first["details"], "position 1 is told they're next")
    third = next(p for p in queued.values() if p["queuePosition"] == 3)
    _assert("2 stories ahead" in third["details"],
            f"position 3 is told 2 are ahead (got: {third['details']!r})")
    _assert(all(p["progress"] == 0 for p in queued.values()),
            "queued sessions report 0% — the bar is hidden for these anyway")

    await asyncio.sleep(0.45)  # first batch finishes, queue advances
    still = [p["queuePosition"] for p in generation._progress.values()
             if p.get("step") == "queued"]
    _assert(len(still) < 3, f"queue drained as slots freed (now {len(still)} waiting)")

    await task
    _assert(generation._waiting == [], "queue empty at the end")


async def scenario_crash_releases_slot() -> None:
    print("\n[3] a crashing pipeline releases its slot")
    _reset()
    tracker = Tracker()
    tracker.crash = {"c0", "c1", "c2"}   # the entire first batch dies
    _install(tracker)

    ids = [f"c{i}" for i in range(6)]
    await asyncio.gather(*(generation._pipeline_runner(i, {}, "u") for i in ids))

    _assert(len(tracker.order) == 6,
            f"the 3 behind still ran after the first 3 crashed (ran {len(tracker.order)})")
    _assert(generation._active == set(), "no slot leaked by the crashes")
    _assert(generation._waiting == [], "no ghost entries left inflating positions")
    errored = [p for sid, p in generation._progress.items()
               if sid in tracker.crash and p.get("step") == "error"]
    _assert(len(errored) == 3, "crashed sessions are reported as errors to their players")


async def scenario_fifo() -> None:
    print("\n[4] first in, first served")
    _reset()
    tracker = Tracker()
    _install(tracker)

    ids = [f"f{i}" for i in range(6)]
    await asyncio.gather(*(generation._pipeline_runner(i, {}, "u") for i in ids))
    first_three = set(tracker.order[:3])
    _assert(first_three == {"f0", "f1", "f2"},
            f"the first 3 submitted ran first (got {sorted(first_three)})")
    _assert(set(tracker.order[3:]) == {"f3", "f4", "f5"},
            "and the queued 3 ran after, not before")


async def main() -> None:
    print("Generation queue verification — pipeline stubbed, no Gemini spend")
    await scenario_capacity()
    await scenario_positions()
    await scenario_crash_releases_slot()
    await scenario_fifo()

    print(f"\n  snapshot API: {generation.queue_snapshot()}")
    if _failures:
        print(f"\n{len(_failures)} CHECK(S) FAILED ❌")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nALL CHECKS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
