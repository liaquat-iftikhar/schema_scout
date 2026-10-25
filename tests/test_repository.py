import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from schema_scout.config import DatabaseConfig
from schema_scout.database.client import DatabaseClient
from schema_scout.database.dialects import adapter_for
from schema_scout.database.sqlalchemy_repository import SqlAlchemyRepository


@pytest.fixture
def repo(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(
            sa.text("CREATE TABLE dim_customer (id INTEGER PRIMARY KEY, email TEXT, tier TEXT)")
        )
        c.execute(
            sa.text(
                "CREATE TABLE fact_orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER, "
                "FOREIGN KEY (customer_id) REFERENCES dim_customer(id))"
            )
        )
        c.execute(
            sa.text("INSERT INTO dim_customer VALUES (1,'a@x.com','gold'),(2,'b@x.com','silver')")
        )
        c.execute(sa.text("INSERT INTO fact_orders VALUES (10,1),(11,1),(12,2),(13,99)"))
    engine.dispose()
    client = DatabaseClient(DatabaseConfig(make_url(url)))
    yield SqlAlchemyRepository(client, "test", ["main"])
    client.close()


def test_list_and_describe(repo):
    names = {t["table_name"] for t in repo.list_tables()}
    assert names == {"dim_customer", "fact_orders"}
    d = repo.describe_table("main.fact_orders")
    fk = next(c for c in d["declared_constraints"] if c["constraint_type"] == "FOREIGN KEY")
    assert (fk["column_name"], fk["ref_table"], fk["ref_column"]) == (
        "customer_id",
        "dim_customer",
        "id",
    )
    assert repo.known_columns["main.fact_orders"][0].name == "order_id"


def test_profile(repo):
    p = repo.profile_table("main.fact_orders")
    assert p["rows"] == 4
    cust = next(c for c in p["columns"] if c["column"] == "customer_id")
    assert cust["approx_distinct"] == 3


def test_join_overlap(repo):
    r = repo.check_join_overlap("main.fact_orders", "customer_id", "main.dim_customer", "id")
    assert r["child_distinct_sampled"] == 3 and r["matched"] == 2
    assert r["match_pct"] == pytest.approx(66.67)
    assert r["parent_is_unique"] is True


def test_sample_values_masks_pii(repo):
    assert "masked" in repo.sample_values("main.dim_customer", "email")["values"]
    assert set(repo.sample_values("main.dim_customer", "tier")["values"]) == {"gold", "silver"}


@pytest.mark.parametrize(
    "table,column",
    [("main.nope", "id"), ("other.dim_customer", "id"), ("main.dim_customer", "id`; drop")],
)
def test_rejects_unknown_or_out_of_scope(repo, table, column):
    with pytest.raises(ValueError):
        repo.sample_values(table, column)


def test_query_history_unsupported_on_sqlite(repo):
    assert "not supported" in repo.get_query_joins()[0]


def test_adapter_selection():
    assert adapter_for("snowflake").query_history_sql(7)
    assert adapter_for("sqlite").query_history_sql(7) is None
