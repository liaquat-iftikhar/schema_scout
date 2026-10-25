from schema_scout.tools.base import DatabaseTool


class ListTablesTool(DatabaseTool):
    name = "list_tables"
    description = "List all tables/views in the in-scope schemas."
    input_schema = {"type": "object", "properties": {}}

    def run(self, **_):
        return self._repo.list_tables()
