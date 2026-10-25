from schema_scout.database.dialects.base import ApproxDistinctMixin, DialectAdapter


class DatabricksAdapter(ApproxDistinctMixin, DialectAdapter):
    name = "databricks"

    def query_history_sql(self, days: int) -> str:
        return (
            "SELECT statement_text FROM system.query.history "
            "WHERE execution_status = 'FINISHED' "
            f"AND start_time >= current_date() - INTERVAL {int(days)} DAYS "
            "AND lower(statement_text) LIKE '%join%' LIMIT 3000"
        )
