"""Background runs with a durable event stream, plus an eval-suite helper.

A run executes on a worker thread. Every event is written to SQLite before it
is streamed, so a page reload replays the whole trace and a finished run looks
the same as a live one.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from typing import Callable, Iterator

from .store import Store


class Runner:
    def __init__(self, store: Store):
        self.store = store
        self.active: dict[int, threading.Thread] = {}

    def start(self, kind: str, title: str, input_: dict,
              job: Callable[[int, Callable[[str, dict], None]], dict]) -> int:
        run_id = self.store.create_run(kind, title, input_)

        def emit(type_: str, payload: dict) -> None:
            self.store.add_event(run_id, type_, payload)

        def work() -> None:
            try:
                output = job(run_id, emit)
                self.store.finish_run(run_id, "done", output)
                emit("run_end", {"status": "done"})
            except Exception as e:  # a failed run is recorded, never left hanging
                self.store.finish_run(run_id, "error", {"error": str(e)})
                emit("run_end", {"status": "error", "error": str(e),
                                 "trace": traceback.format_exc()[-1500:]})
            finally:
                self.active.pop(run_id, None)

        thread = threading.Thread(target=work, daemon=True)
        self.active[run_id] = thread
        thread.start()
        return run_id

    def busy(self, kind: str | None = None) -> bool:
        return bool(self.store.query(
            "SELECT 1 FROM runs WHERE status='running'" + (" AND kind=?" if kind else ""),
            (kind,) if kind else ()))

    def sse(self, run_id: int, after: int = 0) -> Iterator[str]:
        """Server-sent events: replay stored events, then follow until the run ends."""
        last, idle = after, 0.0
        while True:
            batch = self.store.events(run_id, last)
            for ev in batch:
                last = ev["seq"]
                yield f"id: {ev['seq']}\ndata: {json.dumps(ev)}\n\n"
                if ev["type"] == "run_end":
                    return
            if not batch:
                run = self.store.get_run(run_id)
                if not run or run["status"] != "running":
                    return
                idle += 0.35
                if idle > 15:
                    idle = 0.0
                    yield ": keep-alive\n\n"
                time.sleep(0.35)


def run_suite(name: str, cases: list[dict], run_case: Callable[[dict], dict],
              emit: Callable[[str, dict], None] | None = None) -> tuple[dict, list[dict]]:
    """Run each case, collect `{passed, ...}` results, return (summary, results)."""
    results = []
    for i, case in enumerate(cases):
        started = time.time()
        try:
            res = run_case(case)
        except Exception as e:
            res = {"passed": False, "error": str(e)}
        res = {"case": case.get("id", i), "ms": int((time.time() - started) * 1000), **res}
        results.append(res)
        if emit:
            emit("eval_case", {"suite": name, "index": i + 1, "total": len(cases), **res})
    passed = sum(1 for r in results if r.get("passed"))
    summary = {"suite": name, "n": len(results), "passed": passed,
               "pass_rate": round(passed / len(results), 4) if results else 0.0}
    return summary, results
