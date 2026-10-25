from schema_scout.tools.base import DatabaseTool


class GetQueryJoinsTool(DatabaseTool):
    name = "get_query_joins"
    description = (
        "Real JOIN statements from recent query history touching in-scope tables. "
        "Strong evidence of true relationships."
    )
    input_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 40}},
    }

    def run(self, limit: int = 40):
        return self._repo.get_query_joins(limit)
