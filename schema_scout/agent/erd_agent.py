import itertools
import json
from collections.abc import Callable

from schema_scout.agent.prompts import FINISH_NUDGE, SYSTEM_PROMPT, build_task_prompt
from schema_scout.config import AgentConfig
from schema_scout.domain.models import DataModel
from schema_scout.llm.base import LlmClient
from schema_scout.llm.types import Message, ToolCall, ToolResult
from schema_scout.tools.registry import ToolRegistry


class AgentError(RuntimeError):
    """Raised when the agent cannot produce a model."""


class ErdAgent:
    """Runs the tool-use loop, against any LlmClient, until the model submits a DataModel.

    The model's call to the terminal `submit_model` tool is the end signal. `max_turns`, when
    configured, is only a guard rail; without it the loop runs until that signal arrives.
    """

    # Consecutive replies without a tool call (the model ended its turn without submitting)
    # tolerated before giving up. Keeps an unbounded loop from nudging forever.
    MAX_CONSECUTIVE_NUDGES = 3

    def __init__(
        self,
        llm: LlmClient,
        tools: ToolRegistry,
        config: AgentConfig,
        log: Callable[[str], None] = print,
    ):
        self._llm = llm
        self._tools = tools
        self._config = config
        self._log = log

    def run(self, label: str, schemas: list[str], dialect: str) -> DataModel:
        messages = [Message("user", text=build_task_prompt(label, schemas, dialect))]
        limit = self._config.max_turns
        nudges = 0
        for turn in itertools.count():
            if limit is not None and turn >= limit:
                raise AgentError(f"Agent did not submit a model within max_turns={limit}")

            reply = self._llm.complete(SYSTEM_PROMPT, messages, self._tools.api_schemas())
            messages.append(reply)

            if not reply.tool_calls:
                nudges += 1
                if nudges > self.MAX_CONSECUTIVE_NUDGES:
                    raise AgentError(
                        "The model ended its turn repeatedly without calling submit_model"
                    )
                messages.append(Message("user", text=FINISH_NUDGE))
                continue
            nudges = 0

            results: list[ToolResult] = []
            for call in reply.tool_calls:
                outcome = self._execute(turn, call)
                if isinstance(outcome, DataModel):
                    self._log(f"[turn {turn}] model submitted")
                    return outcome
                results.append(outcome)
            messages.append(Message("user", tool_results=results))
        raise AssertionError("unreachable: itertools.count() never ends")  # pragma: no cover

    def _execute(self, turn: int, call: ToolCall) -> DataModel | ToolResult:
        """Run one tool call; returns the DataModel for a valid submission, else a ToolResult."""
        self._log(f"[turn {turn}] {call.name}({json.dumps(call.input)[:120]})")
        try:
            tool = self._tools.get(call.name)
            output = tool.run(**call.input)
            if tool.terminal:
                return output
            content = json.dumps(output, default=str)[: self._config.max_tool_chars]
            return ToolResult(call.id, content)
        except Exception as e:  # surfaced to the model so it can correct itself
            return ToolResult(call.id, f"Error: {e}", is_error=True)
