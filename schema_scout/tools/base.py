from abc import ABC, abstractmethod
from typing import Any

from schema_scout.database.repository import SchemaRepository


class Tool(ABC):
    """A capability exposed to the model. Subclasses declare name, description and schema."""

    name: str
    description: str
    input_schema: dict[str, Any]
    terminal: bool = False  # a terminal tool's result is the agent's final answer

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the tool; the return value must be JSON-serializable unless terminal."""

    def to_api_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class DatabaseTool(Tool, ABC):
    """A tool that reads from the database through a repository."""

    def __init__(self, repository: SchemaRepository):
        self._repo = repository
