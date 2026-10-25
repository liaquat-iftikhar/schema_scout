import pytest

from schema_scout.database.sql_guard import SqlGuard
from schema_scout.database.table_ref import TableRef


@pytest.mark.parametrize(
    "stmt", ["SELECT 1", "  with x as (select 1) select * from x", "SHOW TABLES;"]
)
def test_read_only_allowed(stmt):
    SqlGuard.assert_read_only(stmt)


@pytest.mark.parametrize(
    "stmt", ["DROP TABLE a", "SELECT 1; DROP TABLE a", "insert into a values (1)"]
)
def test_read_only_rejected(stmt):
    with pytest.raises(PermissionError):
        SqlGuard.assert_read_only(stmt)


def test_table_ref_parse():
    assert str(TableRef.parse("sales.orders")) == "sales.orders"
    for bad in ("orders", "a.b.c", ".b", "a."):
        with pytest.raises(ValueError):
            TableRef.parse(bad)
