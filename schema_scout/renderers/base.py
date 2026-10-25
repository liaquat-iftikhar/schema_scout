from abc import ABC, abstractmethod

from schema_scout.domain.models import DataModel


class Renderer(ABC):
    """Turns a DataModel into one output artifact."""

    filename: str

    @abstractmethod
    def render(self, model: DataModel) -> str: ...
