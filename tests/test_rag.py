from agentkit.rag import Index, load_cards, tokenize

DOCS = [
    {"id": "1", "title": "Funding", "text": "Extreme positive funding means longs are crowded and squeezes follow."},
    {"id": "2", "title": "Mixers", "text": "Mixers and peel chains obscure fund flow between wallets."},
    {"id": "3", "title": "Costs", "text": "Fees and slippage erode the edge of high turnover strategies."},
]


def test_tokenize_drops_stopwords():
    assert "the" not in tokenize("the longs are crowded")


def test_search_ranks_relevant_doc_first_with_component_ranks():
    hits = Index(DOCS).search("crowded longs funding", k=2)
    assert hits[0]["id"] == "1"
    assert {"bm25_rank", "cosine_rank", "score"} <= set(hits[0])


def test_search_returns_nothing_for_unrelated_query():
    assert Index(DOCS).search("zzzz qqqq") == []


def test_empty_index_is_safe():
    assert Index([]).search("anything") == []


def test_load_cards_splits_on_headings(tmp_path):
    (tmp_path / "card.md").write_text("# Card\n\n## One\nalpha text\n\n## Two\nbeta text\n")
    docs = load_cards(tmp_path)
    assert [d["title"] for d in docs] == ["Card / One", "Card / Two"]
    assert docs[0]["card"] == "card"
