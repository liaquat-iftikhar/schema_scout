import pytest

from schema_scout.agent import AgentError, ErdAgent
from schema_scout.config import AgentConfig
from schema_scout.domain.models import DataModel
from schema_scout.llm import LlmClient, Message, ToolCall
from schema_scout.tools.base import Tool
from schema_scout.tools.registry import ToolRegistry
from schema_scout.tools.submit_model import SubmitModelTool


class EchoTool(Tool):
    name = "echo"
    description = "echo"
    input_schema = {"type": "object", "properties": {"x": {"type": "string"}}}

    def run(self, x: str):
        return {"echo": x}


class ScriptedLlm(LlmClient):
    """Replays canned assistant turns and records what the agent sent."""

    def __init__(self, replies):
        self._replies = iter(replies)
        self.seen: list[list[Message]] = []

    def complete(self, system, messages, tools):
        self.seen.append(list(messages))
        return next(self._replies)


def agent(llm, max_turns=None):
    registry = ToolRegistry([EchoTool(), SubmitModelTool()])
    return ErdAgent(llm, registry, AgentConfig(max_turns=max_turns), log=lambda _: None)


def call(id, name, **input):
    return Message("assistant", tool_calls=[ToolCall(id, name, input)])


def test_runs_tools_then_returns_submitted_model(submission):
    llm = ScriptedLlm([call("1", "echo", x="hi"), call("2", "submit_model", **submission)])
    model = agent(llm).run("db", ["s"], "sqlite")
    assert isinstance(model, DataModel) and len(model.tables) == 2
    result = llm.seen[1][-1].tool_results[0]
    assert (result.call_id, result.content, result.is_error) == ("1", '{"echo": "hi"}', False)


def test_tool_errors_and_bad_submission_go_back_to_the_model(submission):
    bad = {**submission, "tables": [{"name": "a.b", "kind": "bogus", "primary_key": []}]}
    llm = ScriptedLlm(
        [
            call("1", "no_such_tool"),
            call("2", "submit_model", **bad),
            call("3", "submit_model", **submission),
        ]
    )
    assert isinstance(agent(llm).run("db", ["s"], "sqlite"), DataModel)
    assert llm.seen[1][-1].tool_results[0].is_error
    assert llm.seen[2][-1].tool_results[0].is_error


def test_text_only_reply_is_nudged(submission):
    llm = ScriptedLlm(
        [Message("assistant", text="thinking"), call("1", "submit_model", **submission)]
    )
    agent(llm).run("db", ["s"], "sqlite")
    assert "submit_model" in llm.seen[1][-1].text


def test_turn_limit_is_a_guard_rail_when_configured():
    llm = ScriptedLlm([call(str(i), "echo", x="a") for i in range(10)])
    with pytest.raises(AgentError, match="max_turns=3"):
        agent(llm, max_turns=3).run("db", ["s"], "sqlite")
    assert len(llm.seen) == 3


def test_without_a_limit_runs_until_the_model_submits(submission):
    many = 150  # well past any former hardcoded cap
    llm = ScriptedLlm(
        [call(str(i), "echo", x="a") for i in range(many)]
        + [call("end", "submit_model", **submission)]
    )
    assert isinstance(agent(llm).run("db", ["s"], "sqlite"), DataModel)
    assert len(llm.seen) == many + 1


def test_repeated_turn_ends_without_submitting_give_up():
    llm = ScriptedLlm([Message("assistant", text="done?")] * 10)
    with pytest.raises(AgentError, match="without calling submit_model"):
        agent(llm).run("db", ["s"], "sqlite")
    assert len(llm.seen) == ErdAgent.MAX_CONSECUTIVE_NUDGES + 1


def test_nudge_counter_resets_after_a_tool_call(submission):
    talk = Message("assistant", text="hmm")
    llm = ScriptedLlm(
        [talk, talk, call("1", "echo", x="a"), talk, talk, call("2", "submit_model", **submission)]
    )
    assert isinstance(agent(llm).run("db", ["s"], "sqlite"), DataModel)
