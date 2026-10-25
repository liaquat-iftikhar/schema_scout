from schema_scout.tools.base import DatabaseTool


class ProfileTableTool(DatabaseTool):
    name = "profile_table"
    description = (
        "Row count plus null % and approximate distinct counts per column. "
        "Use to find primary key candidates and grain."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "table": {"type": "string"},
            "max_columns": {"type": "integer", "default": 40},
        },
        "required": ["table"],
    }

    def run(self, table: str, max_columns: int = 40):
        return self._repo.profile_table(table, max_columns)
