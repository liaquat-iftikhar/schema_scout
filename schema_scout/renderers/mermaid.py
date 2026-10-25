import re

from schema_scout.domain.models import Cardinality, DataModel
from schema_scout.renderers.base import Renderer


class MermaidRenderer(Renderer):
    filename = "erd.mmd"

    _SYMBOLS = {
        Cardinality.ONE_TO_MANY: "||--o{",
        Cardinality.ONE_TO_ONE: "||--||",
        Cardinality.MANY_TO_MANY: "}o--o{",
    }

    @staticmethod
    def _id(name: str) -> str:
        return re.sub(r"\W", "_", name)

    def render(self, model: DataModel) -> str:
        pks = model.primary_keys()
        fks = model.foreign_keys()

        lines = ["erDiagram"]
        for table in model.tables:
            pk, fk = pks[table.name], fks.get(table.name, set())
            lines.append(f"  {self._id(table.name)} {{")
            for col in sorted(pk | fk):
                tags = [tag for tag, cols in (("PK", pk), ("FK", fk)) if col in cols]
                lines.append(f"    string {self._id(col)} {','.join(tags)}")
            lines.append("  }")
        for r in model.relationships:
            lines.append(
                f"  {self._id(r.parent_table)} {self._SYMBOLS[r.cardinality]} "
                f'{self._id(r.child_table)} : "{r.child_column}"'
            )
        return "\n".join(lines) + "\n"
