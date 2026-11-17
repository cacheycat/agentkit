"""A small state-graph runtime: named nodes, fixed edges, conditional routes.

A node is `fn(state) -> dict | None`; the returned dict is merged into state.
A key named `_note` is lifted into the trace instead of the state. The loop is
bounded by `max_steps`, so a routing mistake ends a run instead of spinning.
"""
from __future__ import annotations

import time
from typing import Callable

END = "__end__"


class StateGraph:
    def __init__(self, name: str):
        self.name = name
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, str] = {}
        self.routes: dict[str, tuple[Callable[[dict], str], dict[str, str]]] = {}
        self.entry: str | None = None

    def node(self, name: str, fn: Callable[[dict], dict | None], label: str | None = None,
             kind: str = "step") -> "StateGraph":
        """kind is a display hint: step | llm | tool | gate | memory."""
        self.nodes[name] = {"fn": fn, "label": label or name, "kind": kind}
        self.entry = self.entry or name
        return self

    def edge(self, src: str, dst: str) -> "StateGraph":
        self.edges[src] = dst
        return self

    def route(self, src: str, chooser: Callable[[dict], str], targets: dict[str, str]) -> "StateGraph":
        self.routes[src] = (chooser, targets)
        return self

    def describe(self) -> dict:
        edges = [{"from": a, "to": b, "label": ""} for a, b in self.edges.items()]
        for src, (_, targets) in self.routes.items():
            edges += [{"from": src, "to": dst, "label": key} for key, dst in targets.items()]
        return {"name": self.name,
                "nodes": [{"id": n, "label": v["label"], "kind": v["kind"]} for n, v in self.nodes.items()],
                "edges": edges}

    def run(self, state: dict, emit: Callable[[str, dict], None], max_steps: int = 60) -> dict:
        current, steps = self.entry, 0
        while current and current != END:
            steps += 1
            if steps > max_steps:
                emit("budget", {"node": current, "reason": f"step budget of {max_steps} reached"})
                break
            spec = self.nodes[current]
            emit("node_start", {"node": current, "label": spec["label"], "kind": spec["kind"], "step": steps})
            started = time.time()
            update = spec["fn"](state) or {}
            note = update.pop("_note", None)
            state.update(update)
            if current in self.routes:
                chooser, targets = self.routes[current]
                choice = chooser(state)
                nxt = targets.get(choice, END)
            else:
                choice, nxt = None, self.edges.get(current, END)
            emit("node_end", {"node": current, "label": spec["label"], "kind": spec["kind"], "step": steps,
                              "ms": int((time.time() - started) * 1000), "note": note,
                              "route": choice, "next": nxt})
            current = nxt
        return state
