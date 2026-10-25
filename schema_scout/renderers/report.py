from schema_scout.domain.models import DataModel
from schema_scout.renderers.base import Renderer


class ReportRenderer(Renderer):
    filename = "report.md"

    def __init__(self, source: str):
        self._source = source

    def render(self, model: DataModel) -> str:
        lines = [
            f"# Data model report: `{self._source}`\n",
            "## Tables\n",
            "| Table | Kind | Grain | Primary key |",
            "|---|---|---|---|",
        ]
        for t in model.tables:
            lines.append(f"| {t.name} | {t.kind} | {t.grain or ''} | {', '.join(t.primary_key)} |")

        lines += [
            "\n## Relationships\n",
            "| Child | Parent | Cardinality | Confidence | Evidence |",
            "|---|---|---|---|---|",
        ]
        for r in sorted(model.relationships, key=lambda r: -r.confidence):
            lines.append(
                f"| {r.child_ref} | {r.parent_ref} | {r.cardinality} "
                f"| {r.confidence:.2f} | {r.evidence} |"
            )

        lines.append("\n## Issues\n")
        for i in sorted(model.issues, key=lambda i: i.severity.rank):
            lines.append(f"- **{i.severity.value.upper()}** {i.table or ''}: {i.description}")

        lines.append("\n## Recommendations\n")
        ranked = sorted(
            model.recommendations,
            key=lambda r: r.priority if r.priority is not None else 99,
        )
        for n, rec in enumerate(ranked, 1):
            lines.append(f"{n}. **{rec.title}**: {rec.detail}")
        return "\n".join(lines) + "\n"
