import re

from schema_scout.domain.models import Cardinality, ColumnInfo, DataModel
from schema_scout.renderers.base import Renderer


class DbmlRenderer(Renderer):
    filename = "erd.dbml"

    _SYMBOLS = {
        Cardinality.ONE_TO_MANY: "<",
        Cardinality.ONE_TO_ONE: "-",
        Cardinality.MANY_TO_MANY: "<>",
    }

    def __init__(self, columns: dict[str, list[ColumnInfo]]):
        self._columns = columns

    def render(self, model: DataModel) -> str:
        out: list[str] = []
        for table in model.tables:
            pk = set(table.primary_key)
            out.append(f"Table {table.name} {{")
            for col in self._columns.get(table.name, []):
                data_type = re.sub(r"[^A-Za-z0-9_()]", "_", col.data_type)
                name = col.name if re.match(r"^\w+$", col.name) else f'"{col.name}"'
                out.append(f"  {name} {data_type}" + (" [pk]" if col.name in pk else ""))
            if table.grain:
                note = f"Note: 'kind={table.kind}; grain={table.grain}'"
                out.append(f"  {note.replace(chr(34), '')}")
            out.append("}\n")
        for r in model.relationships:
            out.append(f"Ref: {r.parent_ref} {self._SYMBOLS[r.cardinality]} {r.child_ref}")
        return "\n".join(out) + "\n"
