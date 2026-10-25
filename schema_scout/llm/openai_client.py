import json
from typing import Any

from schema_scout.config import LlmConfig
from schema_scout.llm.base import LlmClient
from schema_scout.llm.types import Message, ToolCall


class OpenAiClient(LlmClient):
    """OpenAI Chat Completions; also any OpenAI-compatible server via `base_url`
    (Ollama, vLLM, LM Studio, Azure-compatible gateways, ...)."""

    def __init__(self, config: LlmConfig):
        import openai  # lazy: only needed when this provider is selected

        kwargs: dict[str, Any] = {}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = openai.OpenAI(**kwargs)
        self._model = config.model
        self._max_tokens = config.max_tokens

    def complete(self, system, messages, tools) -> Message:
        response = self._client.chat.completions.create(
            model=self._model,
            max_completion_tokens=self._max_tokens,
            messages=[{"role": "system", "content": system}, *self.to_native(messages)],
            tools=self.tools_to_native(tools),
        )
        return self.from_native(response.choices[0].message)

    @staticmethod
    def tools_to_native(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    @staticmethod
    def to_native(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "assistant":
                msg: dict[str, Any] = {"role": "assistant", "content": m.text or None}
                if m.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.input)},
                        }
                        for c in m.tool_calls
                    ]
                out.append(msg)
            else:
                out += [
                    {"role": "tool", "tool_call_id": r.call_id, "content": r.content}
                    for r in m.tool_results
                ]
                if m.text:
                    out.append({"role": "user", "content": m.text})
        return out

    @staticmethod
    def from_native(message: Any) -> Message:
        calls = []
        for c in message.tool_calls or []:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                # Surfaces to the model as a tool error ("unexpected keyword") so it can retry.
                args = {"_invalid_json_arguments": c.function.arguments}
            calls.append(ToolCall(c.id, c.function.name, args))
        return Message("assistant", text=message.content or "", tool_calls=calls)
