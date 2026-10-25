from schema_scout.database.dialects.base import ApproxDistinctMixin, DialectAdapter


class SnowflakeAdapter(ApproxDistinctMixin, DialectAdapter):
    name = "snowflake"

    def query_history_sql(self, days: int) -> str:
        return (
            "SELECT query_text AS statement_text "
            "FROM snowflake.account_usage.query_history "
            "WHERE execution_status = 'SUCCESS' "
            f"AND start_time >= dateadd(day, -{int(days)}, current_timestamp()) "
            "AND lower(query_text) LIKE '%join%' LIMIT 3000"
        )
