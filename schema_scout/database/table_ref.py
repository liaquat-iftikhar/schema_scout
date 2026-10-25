from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableRef:
    """A 'schema.table' reference. Existence is verified by the repository."""

    schema: str
    name: str

    @classmethod
    def parse(cls, text: str) -> TableRef:
        parts = text.split(".")
        if len(parts) != 2 or not all(parts):
            raise ValueError("Use 'schema.table' format")
        return cls(parts[0], parts[1])

    def __str__(self) -> str:
        return f"{self.schema}.{self.name}"
