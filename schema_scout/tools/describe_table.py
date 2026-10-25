from schema_scout.tools.base import DatabaseTool


class DescribeTableTool(DatabaseTool):
    name = "describe_table"
    description = "Columns, types, comments and declared PK/FK constraints for 'schema.table'."
    input_schema = {
        "type": "object",
        "properties": {"table": {"type": "string"}},
        "required": ["table"],
    }

    def run(self, table: str):
        return self._repo.describe_table(table)
