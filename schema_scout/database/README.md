# Database layer

This package is how Schema Scout talks to a database or data warehouse. It is built on
**SQLAlchemy**, so any platform with a SQLAlchemy dialect works. Three small things are
platform-specific, and they live in `dialects/`.

- [Configuring a database](#configuring-a-database)
- [Dialect cookbook](#dialect-cookbook) (PostgreSQL, MySQL, Snowflake, Databricks, BigQuery, Redshift, SQL Server, Oracle, SQLite)
- [What each platform gets](#what-each-platform-gets)
- [Permissions the database user needs](#permissions-the-database-user-needs)
- [Adding or customising a dialect](#adding-or-customising-a-dialect)
- [Files in this folder](#files-in-this-folder)

## Configuring a database

Everything goes in the `database:` block of the environment you run (`local` or `production`) in
`settings.yaml`, **except credentials, which come from environment variables only**:

```yaml
local:
  database:
    drivername: postgresql+psycopg2   # SQLAlchemy dialect[+driver]
    host: localhost
    port: 5432
    database: analytics
    username: readonly
    query: {sslmode: require}         # optional driver options (always strings)
```
```bash
export SCHEMA_SCOUT_DATABASE__PASSWORD=...   # never in settings.yaml
```

Schema Scout turns the block into a SQLAlchemy URL:

```
drivername://username:<password>@host:port/database?query
```

| Key | Meaning |
|---|---|
| `drivername` | **Required.** SQLAlchemy dialect, optionally with a driver: `postgresql+psycopg2`, `mysql+pymysql`, `snowflake`, ... |
| `host`, `port` | Server address. Some platforms reuse `host` for an account or project name (see below). |
| `database` | Database name. Some platforms use it for more (Snowflake `db/schema`, BigQuery dataset). |
| `username` | Use a **read-only** user. |
| `query` | Extra URL options required by the driver, such as a warehouse, HTTP path or ODBC driver. |

Steps for any platform:

1. **Install the driver:** `pip install -e ".[<extra>]"` (extras are listed in the cookbook).
2. **Set the `database:` block** for your environment.
3. **Set the password** (or token) in `SCHEMA_SCOUT_DATABASE__PASSWORD`.
4. **Choose the schemas** to analyze on the command line: `--schemas public,sales`.

Any key can also be overridden from the environment without editing the file, for example
`SCHEMA_SCOUT_DATABASE__HOST=other-host`. The loader refuses to start if `settings.yaml` contains a
password, token or other secret.

`--schemas` always names the **schemas** (namespaces that hold tables). The mapping per platform:

| Platform | What `--schemas` should be |
|---|---|
| PostgreSQL, Redshift, SQL Server, Oracle | schema names (`public`, `dbo`, ...) |
| MySQL / MariaDB | the database name (MySQL treats schema and database as the same) |
| Snowflake | schema names inside the `database` you configured |
| Databricks | schema names inside the catalog (`query.catalog`, or `--catalog`) |
| BigQuery | dataset names |
| SQLite | `main` |

## Dialect cookbook

Each example is the `database:` block only. Set the password or token in
`SCHEMA_SCOUT_DATABASE__PASSWORD`.

### PostgreSQL

```yaml
database:
  drivername: postgresql+psycopg2
  host: db.example.com
  port: 5432
  database: analytics
  username: schema_scout_readonly
  query: {sslmode: require}
```
Install: `pip install -e ".[postgres]"`. Run: `--schemas public,sales`.

### MySQL / MariaDB

```yaml
database:
  drivername: mysql+pymysql
  host: db.example.com
  port: 3306
  database: shop
  username: schema_scout_readonly
```
Install: `pip install -e ".[mysql]"`. Run: `--schemas shop` (the database name).

### Snowflake

```yaml
database:
  drivername: snowflake
  host: myorg-myaccount          # the account identifier, not a hostname
  database: ANALYTICS/PUBLIC     # <database>/<schema>
  username: SCHEMA_SCOUT
  query: {warehouse: COMPUTE_WH, role: READONLY}
```
Install: `pip install -e ".[snowflake]"`. Run: `--schemas PUBLIC,SALES`.

### Databricks

```yaml
database:
  drivername: databricks
  host: dbc-xxxxxxxx-xxxx.cloud.databricks.com
  username: token                # literally the word "token"
  query:
    http_path: /sql/1.0/warehouses/xxxxxxxxxxxxxxxx
    catalog: main                # Unity Catalog catalog
```
The **password is your personal access token**: `SCHEMA_SCOUT_DATABASE__PASSWORD=dapi...`.
Install: `pip install -e ".[databricks]"`. Run: `--schemas sales,marketing`. To switch catalog
without editing the file, pass `--catalog other_catalog`. It replaces `query.catalog` and only
applies to Databricks.

### BigQuery

```yaml
database:
  drivername: bigquery
  host: my-gcp-project           # the GCP project id
  database: my_dataset           # default dataset
```
Install: `pip install -e ".[bigquery]"`. Run: `--schemas my_dataset,other_dataset`.
BigQuery authenticates with Google credentials rather than a password. Use Application Default
Credentials, for example `GOOGLE_APPLICATION_CREDENTIALS=/path/key.json` in the environment, so
`SCHEMA_SCOUT_DATABASE__PASSWORD` is not needed.

### Amazon Redshift

```yaml
database:
  drivername: redshift+redshift_connector
  host: cluster.abc123.eu-west-1.redshift.amazonaws.com
  port: 5439
  database: dev
  username: schema_scout_readonly
```
Install: `pip install -e ".[redshift]"`. Run: `--schemas public`.

### SQL Server

```yaml
database:
  drivername: mssql+pyodbc
  host: sql.example.com
  port: 1433
  database: Sales
  username: schema_scout_readonly
  query: {driver: "ODBC Driver 18 for SQL Server", TrustServerCertificate: "yes"}
```
Install: `pip install -e ".[mssql]"`. It also needs the Microsoft ODBC driver on the machine
(and in the Docker image). Run: `--schemas dbo`.

### Oracle

```yaml
database:
  drivername: oracle+oracledb
  host: db.example.com
  port: 1521
  username: SCHEMA_SCOUT
  query: {service_name: ORCLPDB1}
```
Install: `pip install -e ".[oracle]"`. Run: `--schemas HR,SALES` (schema names are the owners).

### SQLite

```yaml
database:
  drivername: sqlite
  database: ./example.db
```
No driver to install and no password. Run: `--schemas main`. Handy for trying the tool locally.

### Anything else

If the platform has a SQLAlchemy dialect, it works: install its driver, set `drivername`, and put
whatever its URL needs into `host`, `port`, `database` and `query`. The SQLAlchemy documentation
lists each dialect's URL format. Unknown platforms get the portable defaults below.

## What each platform gets

Metadata (tables, views, columns, primary and foreign keys, comments) comes from SQLAlchemy
reflection and works everywhere. Platform adapters in `dialects/` refine two things:

| SQLAlchemy dialect name | Distinct counts | Query-history mining | Source of query history |
|---|---|---|---|
| `databricks` | approximate | yes | `system.query.history` |
| `snowflake` | approximate | yes | `snowflake.account_usage.query_history` |
| `bigquery` | approximate | no | |
| `postgresql` | exact | yes | `pg_stat_statements` (extension must be enabled; no time window) |
| `mysql`, `mariadb` | exact | yes | `performance_schema.events_statements_summary_by_digest` |
| anything else (Redshift, SQL Server, Oracle, SQLite, ...) | exact | no | |

- **Approximate distinct counts** use `approx_count_distinct`, which is much cheaper on big
  tables.
- **Query-history mining** feeds the `get_query_joins` tool. When it is unsupported or access is
  denied, the tool returns a short note instead of failing, and the agent relies on naming
  patterns, declared constraints and `check_join_overlap`. The model still works well without it,
  but real join history is the strongest evidence, so it is worth enabling where available.

## Permissions the database user needs

Use a dedicated read-only user. It needs:

- **Metadata:** permission to list schemas, tables and columns in the in-scope schemas.
- **Data:** `SELECT` on those tables. Schema Scout runs counts, distinct counts, a few sampled
  values and join-overlap queries.
- **Query history (optional):** access to the history source in the table above. This is often
  restricted. For example, Snowflake's `account_usage` views and Databricks' `system` tables need
  extra grants. Without it everything else still works.

Schema Scout never writes. The client only runs SQLAlchemy `select` constructs, plus raw SQL that
must be a single `SELECT`, `WITH`, `SHOW`, `DESCRIBE` or `EXPLAIN` statement. Table and column
names chosen by the model are checked against the reflected schema and quoted by SQLAlchemy before
use. Still, grant read-only rights at the database level as the real safeguard.

## Adding or customising a dialect

A new platform usually needs **no code**: install the driver and configure it as above. Add an
adapter only to get approximate counts or query-history mining.

1. Create `dialects/mydb.py`:

   ```python
   from schema_scout.database.dialects.base import ApproxDistinctMixin, DialectAdapter


   class MyDbAdapter(ApproxDistinctMixin, DialectAdapter):   # drop the mixin for exact counts
       name = "mydb"

       def query_history_sql(self, days: int) -> str:
           # must return a column named statement_text; return None if unsupported
           return (
               "SELECT sql_text AS statement_text FROM mydb.query_log "
               f"WHERE ts >= now() - interval '{int(days)} days' "
               "AND lower(sql_text) LIKE '%join%' LIMIT 3000"
           )
   ```

2. Register it in `dialects/registry.py`, keyed by the **SQLAlchemy dialect name**, which is the
   part of `drivername` before the `+` (`postgresql+psycopg2` → `postgresql`):

   ```python
   _ADAPTERS = {..., "mydb": MyDbAdapter()}
   ```

Query-history SQL is sent as a raw statement, so it must pass the read-only guard. Build it only
from values you control (as above, `int(days)`), never from model input.

## Files in this folder

| File | Role |
|---|---|
| `client.py` | `DatabaseClient`: creates the SQLAlchemy engine from the config, exposes the inspector, runs guarded queries |
| `repository.py` | `SchemaRepository`: the interface the agent's tools depend on (list, describe, profile, sample, join overlap, query joins) |
| `sqlalchemy_repository.py` | `SqlAlchemyRepository`: the portable implementation, using reflection and SQLAlchemy Core |
| `dialects/` | `DialectAdapter` base class, one adapter per platform, and `registry.py` (dialect name → adapter) |
| `sql_guard.py` | `SqlGuard`: allows only a single read-only raw statement |
| `table_ref.py` | `TableRef`: parses and holds a `schema.table` reference |
| `pii_masker.py` | `PiiMasker`: flags personal-looking column names so their values are never sampled |

The tools themselves are documented in [`../tools/README.md`](../tools/README.md).
