from __future__ import annotations

from collections.abc import Iterable

from schema_scout.database.repository import SchemaRepository
from schema_scout.tools.base import Tool
from schema_scout.tools.check_join_overlap import CheckJoinOverlapTool
from schema_scout.tools.describe_table import DescribeTableTool
from schema_scout.tools.get_query_joins import GetQueryJoinsTool
from schema_scout.tools.list_tables import ListTablesTool
from schema_scout.tools.profile_table import ProfileTableTool
from schema_scout.tools.sample_values import SampleValuesTool
from schema_scout.tools.submit_model import SubmitModelTool


class ToolRegistry:
    """Lookup and API-schema export for the tools available to the agent."""

    def __init__(self, tools: Iterable[Tool]):
        self._tools = {t.name: t for t in tools}

    @classmethod
    def for_database(cls, repository: SchemaRepository) -> ToolRegistry:
        return cls(
            [
                ListTablesTool(repository),
                DescribeTableTool(repository),
                ProfileTableTool(repository),
                SampleValuesTool(repository),
                CheckJoinOverlapTool(repository),
                GetQueryJoinsTool(repository),
                SubmitModelTool(),
            ]
        )

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"Unknown tool: {name}") from None

    def api_schemas(self) -> list[dict]:
        return [t.to_api_schema() for t in self._tools.values()]
