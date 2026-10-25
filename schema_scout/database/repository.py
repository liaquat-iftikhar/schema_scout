from abc import ABC, abstractmethod

from schema_scout.domain.models import ColumnInfo


class SchemaRepository(ABC):
    """What the agent's tools need from a database. Implementations must be read-only."""

    label: str
    schemas: list[str]
    dialect_name: str

    @property
    @abstractmethod
    def known_columns(self) -> dict[str, list[ColumnInfo]]:
        """Columns of every table described so far (used by the DBML renderer)."""

    @abstractmethod
    def list_tables(self) -> list[dict]: ...

    @abstractmethod
    def describe_table(self, table: str) -> dict: ...

    @abstractmethod
    def profile_table(self, table: str, max_columns: int = 40) -> dict: ...

    @abstractmethod
    def sample_values(self, table: str, column: str, n: int = 10) -> dict: ...

    @abstractmethod
    def check_join_overlap(
        self,
        child_table: str,
        child_column: str,
        parent_table: str,
        parent_column: str,
        sample_size: int = 50_000,
    ) -> dict: ...

    @abstractmethod
    def get_query_joins(self, limit: int = 40, days: int = 30) -> list[str]: ...
