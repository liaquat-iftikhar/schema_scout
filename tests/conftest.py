import pytest

from schema_scout.domain.models import DataModel


@pytest.fixture
def submission() -> dict:
    return {
        "tables": [
            {"name": "sales.dim_customer", "kind": "dimension", "primary_key": ["id"]},
            {
                "name": "sales.fact_orders",
                "kind": "fact",
                "primary_key": ["order_id"],
                "grain": "one row per order",
            },
        ],
        "relationships": [
            {
                "child_table": "sales.fact_orders",
                "child_column": "customer_id",
                "parent_table": "sales.dim_customer",
                "parent_column": "id",
                "cardinality": "1:N",
                "confidence": 0.7,
                "evidence": "98% overlap",
            }
        ],
        "issues": [{"severity": "high", "table": "sales.fact_orders", "description": "no FK"}],
        "recommendations": [{"title": "Declare FKs", "detail": "Add constraints", "priority": 1}],
    }


@pytest.fixture
def model(submission) -> DataModel:
    return DataModel.from_dict(submission)
