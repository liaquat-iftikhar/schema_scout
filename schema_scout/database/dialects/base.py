import sqlalchemy as sa
from sqlalchemy.sql.elements import ColumnElement


class DialectAdapter:
    """Platform-specific behaviour. The defaults are portable and work on any database."""

    name = "generic"

    def distinct_count(self, column: ColumnElement) -> ColumnElement:
        """Distinct count of a column; exact by default, approximate where the platform offers it."""
        return sa.func.count(sa.distinct(column))

    def query_history_sql(self, days: int) -> str | None:
        """SQL returning a `statement_text` column of recent JOIN queries, or None if unsupported."""
        return None


class ApproxDistinctMixin:
    def distinct_count(self, column: ColumnElement) -> ColumnElement:
        return sa.func.approx_count_distinct(column)
