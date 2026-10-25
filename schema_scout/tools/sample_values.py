from schema_scout.tools.base import DatabaseTool


class SampleValuesTool(DatabaseTool):
    name = "sample_values"
    description = "A few distinct values of a column (PII-looking columns are masked)."
    input_schema = {
        "type": "object",
        "properties": {
            "table": {"type": "string"},
            "column": {"type": "string"},
            "n": {"type": "integer", "default": 10},
        },
        "required": ["table", "column"],
    }

    def run(self, table: str, column: str, n: int = 10):
        return self._repo.sample_values(table, column, n)
