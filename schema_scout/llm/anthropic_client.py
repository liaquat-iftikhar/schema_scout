from typing import Any

from schema_scout.config import LlmConfig
from schema_scout.llm.base import LlmClient
from schema_scout.llm.types import Message, ToolCall


class AnthropicClient(LlmClient):
    def __init__(self, config: LlmConfig):
        import anthropic  # lazy: only needed when this provider is selected

        kwargs: dict[str, Any] = {}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = anthropic.Anthropic(**kwargs)
        self._model = config.model
        self._max_tokens = config.max_tokens

    def complete(self, system, messages, tools) -> Message:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            tools=tools,  # the neutral schema already matches Anthropic's
            messages=self.to_native(messages),
        )
        return self.from_native(response.content)

    @staticmethod
    def to_native(messages: list[Message]) -> list[dict[str, Any]]:
        out = []
        for m in messages:
            blocks: list[dict[str, Any]] = []
            if m.role == "assistant":
                if m.text:
                    blocks.append({"type": "text", "text": m.text})
                blocks += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input}
                    for c in m.tool_calls
                ]
            else:
                for r in m.tool_results:  # tool_result blocks must precede any text
                    block = {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content}
                    if r.is_error:
                        block["is_error"] = True
                    blocks.append(block)
                if m.text:
                    blocks.append({"type": "text", "text": m.text})
            out.append({"role": m.role, "content": blocks or [{"type": "text", "text": "(empty)"}]})
        return out

    @staticmethod
    def from_native(content: list[Any]) -> Message:
        text = "".join(b.text for b in content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in content if b.type == "tool_use"]
        return Message("assistant", text=text, tool_calls=calls)
