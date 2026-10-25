from abc import ABC, abstractmethod
from typing import Any

from schema_scout.llm.types import Message


class LlmClient(ABC):
    """One chat-completion step with tool use. Implementations translate to a provider's API."""

    @abstractmethod
    def complete(
        self, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> Message:
        """Return the assistant's next turn.

        `tools` are neutral schemas: {"name", "description", "input_schema"}.
        """
