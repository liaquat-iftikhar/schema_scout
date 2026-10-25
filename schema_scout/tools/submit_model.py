from typing import Any

from schema_scout.domain.models import Cardinality, DataModel, Severity, TableKind
from schema_scout.tools.base import Tool


def _enum_values(enum_cls) -> list[str]:
    return [m.value for m in enum_cls]


class SubmitModelTool(Tool):
    """Terminal tool: the model's structured answer, validated into a DataModel."""

    name = "submit_model"
    description = "Submit the final data model. Call exactly once, when investigation is complete."
    terminal = True
    input_schema = {
        "type": "object",
        "properties": {
            "tables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "schema.table"},
                        "kind": {"type": "string", "enum": _enum_values(TableKind)},
                        "grain": {"type": "string"},
                        "primary_key": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "string"},
                    },
                    "required": ["name", "kind", "primary_key"],
                },
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "child_table": {"type": "string"},
                        "child_column": {"type": "string"},
                        "parent_table": {"type": "string"},
                        "parent_column": {"type": "string"},
                        "cardinality": {
                            "type": "string",
                            "enum": _enum_values(Cardinality),
                            "description": "parent:child",
                        },
                        "confidence": {"type": "number", "description": "0..1"},
                        "declared": {"type": "boolean"},
                        "evidence": {"type": "string"},
                    },
                    "required": [
                        "child_table",
                        "child_column",
                        "parent_table",
                        "parent_column",
                        "cardinality",
                        "confidence",
                        "evidence",
                    ],
                },
            },
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string", "enum": _enum_values(Severity)},
                        "table": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["severity", "description"],
                },
            },
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "priority": {"type": "integer"},
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                    "required": ["title", "detail"],
                },
            },
        },
        "required": ["tables", "relationships", "issues", "recommendations"],
    }

    def run(self, **submission: Any) -> DataModel:
        return DataModel.from_dict(submission)
