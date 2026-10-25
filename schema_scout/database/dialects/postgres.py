from schema_scout.database.dialects.base import DialectAdapter


class PostgresAdapter(DialectAdapter):
    """Also used for Redshift-style dialects that expose pg_stat_statements-like views."""

    name = "postgresql"

    def query_history_sql(self, days: int) -> str:
        # pg_stat_statements has no time window; requires the extension to be enabled.
        return (
            "SELECT query AS statement_text FROM pg_stat_statements "
            "WHERE lower(query) LIKE '%join%' LIMIT 3000"
        )
