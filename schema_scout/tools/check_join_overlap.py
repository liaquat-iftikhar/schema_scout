from schema_scout.tools.base import DatabaseTool


class CheckJoinOverlapTool(DatabaseTool):
    name = "check_join_overlap"
    description = (
        "Validate a candidate FK: share of distinct child values found in the parent "
        "column, and whether the parent column is unique."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "child_table": {"type": "string"},
            "child_column": {"type": "string"},
            "parent_table": {"type": "string"},
            "parent_column": {"type": "string"},
            "sample_size": {"type": "integer", "default": 50000},
        },
        "required": ["child_table", "child_column", "parent_table", "parent_column"],
    }

    def run(
        self,
        child_table: str,
        child_column: str,
        parent_table: str,
        parent_column: str,
        sample_size: int = 50_000,
    ):
        return self._repo.check_join_overlap(
            child_table, child_column, parent_table, parent_column, sample_size
        )
