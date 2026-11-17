"""A whole agent in 40 lines: recall -> decide -> learn, with no API key needed.

    python examples/hello.py
"""
import tempfile
from pathlib import Path

from agentkit import END, LLM, Memory, StateGraph, Store

store = Store(Path(tempfile.mkdtemp()) / "demo.db")
memory = Memory(store)
llm = LLM(provider=None)  # no provider: every call uses its deterministic fallback

memory.add("lesson", "Crowded longs with extreme funding tend to get squeezed")
memory.add("lesson", "Tight stops on volatile assets get whipsawed by noise")


def recall(state):
    hits = memory.search(state["question"], k=1)
    return {"recalled": hits, "_note": f"recalled {len(hits)} lesson(s)"}


def decide(state):
    out = llm.json("decide", "You are a desk analyst.", state["question"],
                   {"type": "object", "required": ["stance"], "properties": {"stance": {"type": "string"}}},
                   fallback=lambda: {"stance": "flat"})
    return {"stance": out["stance"]}


def learn(state):
    memory.feedback([h["id"] for h in state["recalled"]], good=True)  # the lesson helped


g = (StateGraph("hello").node("recall", recall, kind="memory").node("decide", decide, kind="llm")
     .node("learn", learn, kind="memory"))
g.edge("recall", "decide").edge("decide", "learn").edge("learn", END)

final = g.run({"question": "Are longs crowded given extreme funding?"},
              lambda kind, p: print(f"{kind:<11}{p.get('node', '')}  {p.get('note') or ''}"))
print("stance:", final["stance"], "| lesson utility now:", memory.all("lesson")[-1]["utility"])
