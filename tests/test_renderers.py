from schema_scout.domain.models import ColumnInfo
from schema_scout.output.relationship_reviewer import RelationshipReviewer
from schema_scout.renderers import DbmlRenderer, MermaidRenderer, ReportRenderer


def test_mermaid(model):
    out = MermaidRenderer().render(model)
    assert out.startswith("erDiagram")
    assert "sales_dim_customer ||--o{ sales_fact_orders" in out
    assert "string customer_id FK" in out
    assert "string order_id PK" in out


def test_dbml(model):
    columns = {"sales.dim_customer": [ColumnInfo("id", "bigint")]}
    out = DbmlRenderer(columns).render(model)
    assert "id bigint [pk]" in out
    assert "Ref: sales.dim_customer.id < sales.fact_orders.customer_id" in out


def test_report(model):
    out = ReportRenderer("main").render(model)
    assert "# Data model report: `main`" in out
    assert "**HIGH** sales.fact_orders: no FK" in out
    assert "1. **Declare FKs**" in out


def test_reviewer_drops_rejected_low_confidence(model):
    kept = RelationshipReviewer(0.85, ask=lambda _: "n", say=lambda _: None).review(model)
    assert kept.relationships == []


def test_reviewer_keeps_confirmed_and_declared(model):
    kept = RelationshipReviewer(0.85, ask=lambda _: "y", say=lambda _: None).review(model)
    assert len(kept.relationships) == 1
    model.relationships[0].declared = True
    asked = []
    RelationshipReviewer(0.85, ask=lambda p: asked.append(p) or "n", say=lambda _: None).review(
        model
    )
    assert asked == []
