import pytest

from agentkit.llm import LLMError, check_shape, extract_json


@pytest.mark.parametrize("text, expected", [
    ('{"a": 1}', {"a": 1}),
    ('Sure!\n```json\n{"a": 1}\n```\nDone', {"a": 1}),
    ('```\n{"a": 1}\n```', {"a": 1}),
    ('prose {"a": [1, 2]} trailing', {"a": [1, 2]}),
    ("a list: [1, 2]", [1, 2]),
])
def test_extract_json_tolerates_wrapping(text, expected):
    assert extract_json(text) == expected


@pytest.mark.parametrize("text", ["no json here", '{"a":'])
def test_extract_json_rejects_garbage(text):
    with pytest.raises(LLMError):
        extract_json(text)


SCHEMA = {"type": "object", "required": ["n"], "properties": {"n": {"type": "integer"}}}


def test_check_shape_accepts_valid():
    check_shape({"n": 3}, SCHEMA)


def test_check_shape_missing_key():
    with pytest.raises(LLMError):
        check_shape({}, SCHEMA)


def test_check_shape_rejects_bool_as_integer():
    with pytest.raises(LLMError):
        check_shape({"n": True}, SCHEMA)
