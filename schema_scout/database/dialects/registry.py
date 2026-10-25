from schema_scout.database.dialects.base import DialectAdapter
from schema_scout.database.dialects.bigquery import BigQueryAdapter
from schema_scout.database.dialects.databricks import DatabricksAdapter
from schema_scout.database.dialects.mysql import MySqlAdapter
from schema_scout.database.dialects.postgres import PostgresAdapter
from schema_scout.database.dialects.snowflake import SnowflakeAdapter

_ADAPTERS: dict[str, DialectAdapter] = {
    "databricks": DatabricksAdapter(),
    "snowflake": SnowflakeAdapter(),
    "bigquery": BigQueryAdapter(),
    "postgresql": PostgresAdapter(),
    "mysql": MySqlAdapter(),
    "mariadb": MySqlAdapter(),
}
_GENERIC = DialectAdapter()


def adapter_for(dialect_name: str) -> DialectAdapter:
    """Platform adapter for a SQLAlchemy dialect name; any unknown platform gets the portable default."""
    return _ADAPTERS.get(dialect_name, _GENERIC)
