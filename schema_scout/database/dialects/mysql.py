from schema_scout.database.dialects.base import DialectAdapter


class MySqlAdapter(DialectAdapter):
    name = "mysql"

    def query_history_sql(self, days: int) -> str:
        return (
            "SELECT digest_text AS statement_text "
            "FROM performance_schema.events_statements_summary_by_digest "
            "WHERE lower(digest_text) LIKE '%join%' LIMIT 3000"
        )
