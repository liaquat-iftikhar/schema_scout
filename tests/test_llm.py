from types import SimpleNamespace as NS

import pytest

from schema_scout.config import ConfigError, LlmConfig
from schema_scout.llm import Message, ToolCall, ToolResult, available_providers, create_llm_client
from schema_scout.llm.anthropic_client import AnthropicClient
from schema_scout.llm.openai_client import OpenAiClient

HISTORY = [
    Message("user", text="go"),
    Message("assistant", text="checking", tool_calls=[ToolCall("c1", "list_tables", {})]),
    Message(
        "user", tool_results=[ToolResult("c1", "[]"), ToolResult("c2", "Error: x", is_error=True)]
    ),
    Message("user", text="finish"),
]


def test_anthropic_to_native():
    out = AnthropicClient.to_native(HISTORY)
    assert out[1]["content"] == [
        {"type": "text", "text": "checking"},
        {"type": "tool_use", "id": "c1", "name": "list_tables", "input": {}},
    ]
    assert out[2]["content"][0] == {"type": "tool_result", "tool_use_id": "c1", "content": "[]"}
    assert out[2]["content"][1]["is_error"] is True


def test_anthropic_from_native():
    blocks = [
        NS(type="text", text="hi"),
        NS(type="tool_use", id="t1", name="describe_table", input={"table": "a.b"}),
    ]
    msg = AnthropicClient.from_native(blocks)
    assert msg.text == "hi"
    assert msg.tool_calls == [ToolCall("t1", "describe_table", {"table": "a.b"})]


def test_openai_to_native():
    out = OpenAiClient.to_native(HISTORY)
    assert out[1]["tool_calls"][0]["function"] == {"name": "list_tables", "arguments": "{}"}
    assert [m["role"] for m in out] == ["user", "assistant", "tool", "tool", "user"]
    assert out[2]["tool_call_id"] == "c1"


def test_openai_tools_to_native():
    t = OpenAiClient.tools_to_native(
        [{"name": "n", "description": "d", "input_schema": {"type": "object"}}]
    )
    assert t == [
        {
            "type": "function",
            "function": {"name": "n", "description": "d", "parameters": {"type": "object"}},
        }
    ]


def test_openai_from_native_and_bad_json():
    def call(args):
        return NS(id="x", function=NS(name="f", arguments=args))

    msg = OpenAiClient.from_native(NS(content=None, tool_calls=[call('{"a": 1}'), call("{oops")]))
    assert msg.tool_calls[0].input == {"a": 1}
    assert "_invalid_json_arguments" in msg.tool_calls[1].input


def test_factory_rejects_unknown_provider():
    assert available_providers() == ["anthropic", "openai"]
    with pytest.raises(ConfigError, match="Unknown llm.provider"):
        create_llm_client(LlmConfig(provider="nope"))
