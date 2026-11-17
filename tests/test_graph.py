from agentkit.graph import END, StateGraph


def collect():
    events = []
    return events, lambda t, p: events.append((t, p))


def test_linear_run_merges_state_and_lifts_notes():
    g = StateGraph("t").node("a", lambda s: {"x": 1, "_note": "hi"}).node("b", lambda s: {"y": s["x"] + 1})
    g.edge("a", "b").edge("b", END)
    events, emit = collect()
    state = g.run({}, emit)
    assert state == {"x": 1, "y": 2}
    ends = [p for t, p in events if t == "node_end"]
    assert ends[0]["note"] == "hi" and ends[1]["next"] == END


def test_conditional_route_picks_branch():
    g = (StateGraph("t").node("start", lambda s: None)
         .node("yes", lambda s: {"hit": "yes"}).node("no", lambda s: {"hit": "no"}))
    g.route("start", lambda s: "yes" if s["go"] else "no", {"yes": "yes", "no": "no"})
    assert g.run({"go": True}, collect()[1])["hit"] == "yes"
    assert g.run({"go": False}, collect()[1])["hit"] == "no"


def test_step_budget_stops_a_cycle():
    g = StateGraph("loop").node("a", lambda s: {"n": s.get("n", 0) + 1}).edge("a", "a")
    events, emit = collect()
    state = g.run({}, emit, max_steps=5)
    assert state["n"] == 5
    assert events[-1][0] == "budget"


def test_describe_lists_nodes_and_labelled_edges():
    g = StateGraph("t").node("a", lambda s: None).node("b", lambda s: None)
    g.route("a", lambda s: "k", {"k": "b"})
    d = g.describe()
    assert {n["id"] for n in d["nodes"]} == {"a", "b"}
    assert d["edges"] == [{"from": "a", "to": "b", "label": "k"}]
