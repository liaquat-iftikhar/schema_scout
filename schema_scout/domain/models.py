from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class TableKind(_StrEnum):
    FACT = "fact"
    DIMENSION = "dimension"
    BRIDGE = "bridge"
    STAGING = "staging"
    OTHER = "other"


class Cardinality(_StrEnum):
    """Written parent:child."""

    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_MANY = "N:M"


class Severity(_StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {"high": 0, "medium": 1, "low": 2}[self.value]


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str


@dataclass
class Table:
    name: str  # schema.table
    kind: TableKind
    primary_key: list[str]
    grain: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Table:
        return cls(
            name=data["name"],
            kind=TableKind(data["kind"]),
            primary_key=list(data["primary_key"]),
            grain=data.get("grain"),
            notes=data.get("notes"),
        )


@dataclass
class Relationship:
    child_table: str
    child_column: str
    parent_table: str
    parent_column: str
    cardinality: Cardinality
    confidence: float
    evidence: str
    declared: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Relationship:
        confidence = float(data["confidence"])
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be within 0..1, got {confidence}")
        return cls(
            child_table=data["child_table"],
            child_column=data["child_column"],
            parent_table=data["parent_table"],
            parent_column=data["parent_column"],
            cardinality=Cardinality(data["cardinality"]),
            confidence=confidence,
            evidence=data["evidence"],
            declared=bool(data.get("declared", False)),
        )

    @property
    def child_ref(self) -> str:
        return f"{self.child_table}.{self.child_column}"

    @property
    def parent_ref(self) -> str:
        return f"{self.parent_table}.{self.parent_column}"

    def needs_review(self, threshold: float) -> bool:
        return not self.declared and self.confidence < threshold


@dataclass
class Issue:
    severity: Severity
    description: str
    table: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Issue:
        return cls(
            severity=Severity(data["severity"]),
            description=data["description"],
            table=data.get("table"),
        )


@dataclass
class Recommendation:
    title: str
    detail: str
    priority: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Recommendation:
        return cls(
            title=data["title"],
            detail=data["detail"],
            priority=data.get("priority"),
        )


@dataclass
class DataModel:
    tables: list[Table] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataModel:
        """Build a model from the agent's submission; raises KeyError/ValueError if malformed."""
        return cls(
            tables=[Table.from_dict(t) for t in data["tables"]],
            relationships=[Relationship.from_dict(r) for r in data["relationships"]],
            issues=[Issue.from_dict(i) for i in data["issues"]],
            recommendations=[Recommendation.from_dict(r) for r in data["recommendations"]],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_relationships(self, relationships: list[Relationship]) -> DataModel:
        return replace(self, relationships=relationships)

    def primary_keys(self) -> dict[str, set[str]]:
        return {t.name: set(t.primary_key) for t in self.tables}

    def foreign_keys(self) -> dict[str, set[str]]:
        fks: dict[str, set[str]] = {}
        for r in self.relationships:
            fks.setdefault(r.child_table, set()).add(r.child_column)
        return fks
