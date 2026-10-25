import sqlalchemy as sa
from sqlalchemy.engine import Inspector
from sqlalchemy.sql import Select

from schema_scout.config import DatabaseConfig
from schema_scout.database.sql_guard import SqlGuard


class DatabaseClient:
    """Read-only access to any SQLAlchemy-supported database or warehouse."""

    def __init__(self, config: DatabaseConfig):
        self._engine = sa.create_engine(config.url)

    @property
    def dialect(self) -> sa.engine.Dialect:
        return self._engine.dialect

    @property
    def dialect_name(self) -> str:
        return self._engine.dialect.name

    @property
    def database_name(self) -> str | None:
        return self._engine.url.database

    def inspector(self) -> Inspector:
        return sa.inspect(self._engine)

    def fetch(self, statement: Select | str) -> list[dict]:
        """Run a SQLAlchemy select or a guarded raw read-only statement."""
        if isinstance(statement, str):
            SqlGuard.assert_read_only(statement)
            statement = sa.text(statement)
        elif not isinstance(statement, Select):
            raise PermissionError("Only select statements are allowed")
        with self._engine.connect() as conn:
            return [dict(row) for row in conn.execute(statement).mappings().all()]

    def close(self) -> None:
        self._engine.dispose()
