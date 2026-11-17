import pytest

from agentkit.memory import Memory, utility
from agentkit.store import Store


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "t.db")


def test_utility_is_laplace_smoothed():
    assert utility(0, 0) == 0.5
    assert utility(3, 0) > utility(0, 0) > utility(0, 3)


def test_add_suppresses_near_duplicates(store):
    m = Memory(store)
    a = m.add("lesson", "Tight stops on volatile assets get whipsawed by noise")
    b = m.add("lesson", "tight stops on volatile assets get whipsawed by noise!")
    assert a == b and len(m.all("lesson")) == 1


def test_feedback_moves_ranking(store):
    m = Memory(store)
    good = m.add("lesson", "wide trailing stops help trend following on volatile assets")
    bad = m.add("lesson", "narrow trailing stops hurt trend following on volatile assets quickly")
    m.feedback([good], True)
    m.feedback([bad], False)
    m.feedback([bad], False)
    hits = m.search("trailing stops trend following volatile", k=2, touch=False)
    assert hits[0]["id"] == good


def test_search_touch_increments_uses(store):
    m = Memory(store)
    i = m.add("lesson", "funding extremes precede squeezes")
    m.search("funding squeezes", k=1)
    assert next(r for r in m.all() if r["id"] == i)["uses"] == 1


def test_running_runs_are_marked_interrupted_on_reopen(tmp_path):
    s = Store(tmp_path / "r.db")
    rid = s.create_run("demo", "t", {})
    s.add_event(rid, "x", {"a": 1})
    s2 = Store(tmp_path / "r.db")
    assert s2.get_run(rid)["status"] == "interrupted"
    assert len(s2.events(rid)) == 1
