# Agent tools

The tools are the only way the LLM can look at your database. Each tool is a small class that
the agent describes to the model (name, description, JSON input schema). When the model asks for a
tool, `ErdAgent` runs it and sends the result back.

All database tools are **read-only**, and they only accept tables and columns that exist in the
schemas passed with `--schemas`.

## The tools at a glance

| Tool | File | Purpose | Typical use |
|---|---|---|---|
| [`list_tables`](#list_tables) | `list_tables.py` | List tables and views in scope | first call |
| [`describe_table`](#describe_table) | `describe_table.py` | Columns, types, comments, declared PK/FK | once per table |
| [`profile_table`](#profile_table) | `profile_table.py` | Row count, null %, distinct counts | find primary keys and grain |
| [`sample_values`](#sample_values) | `sample_values.py` | A few distinct values of a column | understand what a column holds |
| [`check_join_overlap`](#check_join_overlap) | `check_join_overlap.py` | Test a candidate foreign key against real data | validate every guessed relationship |
| [`get_query_joins`](#get_query_joins) | `get_query_joins.py` | Real JOINs from query history | strong evidence of true relationships |
| [`submit_model`](#submit_model) | `submit_model.py` | Submit the final model | **ends the run** |

Typical order, as laid out in the system prompt (`agent/prompts.py`):
`list_tables` → `describe_table` (every table) → `profile_table` → `get_query_joins` →
`check_join_overlap` (every guessed relationship) → `submit_model`.

Table names are always written `schema.table`, for example `sales.orders`.

---

## `list_tables`

Lists every table and view in the in-scope schemas.

**Input:** none.

**Output:**
```json
[
  {"table_schema": "sales", "table_name": "customers", "table_type": "BASE TABLE"},
  {"table_schema": "sales", "table_name": "orders_v", "table_type": "VIEW"}
]
```

---

## `describe_table`

Structure of one table, including constraints the database itself declares.

**Input:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `table` | string | yes | `schema.table` |

**Output:**
```json
{
  "table": "sales.orders",
  "comment": "One row per order",
  "columns": [
    {"column_name": "order_id", "data_type": "BIGINT", "is_nullable": false, "comment": null},
    {"column_name": "customer_id", "data_type": "BIGINT", "is_nullable": true, "comment": null}
  ],
  "declared_constraints": [
    {"constraint_name": "orders_pk", "constraint_type": "PRIMARY KEY", "column_name": "order_id"},
    {"constraint_name": "fk_cust", "constraint_type": "FOREIGN KEY", "column_name": "customer_id",
     "ref_schema": "sales", "ref_table": "customers", "ref_column": "id"}
  ]
}
```

Comments and constraints are optional on many platforms. If they cannot be read, `comment` is
`null` and `declared_constraints` holds a single `{"note": "could not read constraints: ..."}`.

---

## `profile_table`

One query that returns the row count and, per column, how many values are null and how many are
distinct. A column whose uniqueness is close to 1.0 with few nulls is a primary key candidate.

**Input:**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `table` | string | yes | | `schema.table` |
| `max_columns` | integer | no | 40 | Only the first N columns are profiled, to keep the query cheap |

**Output:**
```json
{
  "table": "sales.orders",
  "rows": 120000,
  "columns": [
    {"column": "order_id", "null_pct": 0.0, "approx_distinct": 120000, "uniqueness": 1.0},
    {"column": "customer_id", "null_pct": 1.2, "approx_distinct": 8500, "uniqueness": 0.0717}
  ]
}
```

`uniqueness` is `approx_distinct / non-null count`. Distinct counts are exact by default and
approximate on Databricks, Snowflake and BigQuery.

---

## `sample_values`

A few distinct, non-null values of one column, to see what it really contains (IDs, codes,
dates, ...).

**Input:**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `table` | string | yes | | `schema.table` |
| `column` | string | yes | | |
| `n` | integer | no | 10 | Clamped to 1..25 |

**Output:**
```json
{"column": "status", "values": ["NEW", "PAID", "SHIPPED"]}
```

Each value is cut to 60 characters. **PII protection:** if the column name looks personal
(email, phone, ssn, address, birth, first/last/full name, card, iban, password, token, secret, ip
address, ...), no data is read and the tool returns
`{"column": "email", "values": "<masked: looks like PII>"}`. The rule lives in
`database/pii_masker.py`.

---

## `check_join_overlap`

Tests a guessed foreign key: how many of the child column's distinct values exist in the parent
column, and is the parent column unique? This is what turns a naming-pattern guess into evidence.

**Input:**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `child_table` | string | yes | | table holding the foreign key |
| `child_column` | string | yes | | |
| `parent_table` | string | yes | | table being referenced |
| `parent_column` | string | yes | | |
| `sample_size` | integer | no | 50000 | Distinct child values to test; clamped to 1,000..200,000 |

**Output:**
```json
{
  "child_distinct_sampled": 8500,
  "matched": 8466,
  "parent_rows": 9000,
  "parent_distinct": 9000,
  "match_pct": 99.6,
  "parent_is_unique": true
}
```

How the agent reads it (from the system prompt): accept a relationship at **95% or more with a
unique parent**; flag **80-95%** as low confidence (orphan rows); drop it below 80% unless query
history strongly supports it.

---

## `get_query_joins`

Mines the platform's query history for real `JOIN` statements that touch in-scope tables. People
joining two tables in practice is strong evidence that they are related.

**Input:**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `limit` | integer | no | 40 | Capped at 80 |

**Output:** a list of SQL strings, de-duplicated (literals are ignored when comparing) and
truncated to 700 characters each:
```json
["SELECT ... FROM sales.orders o JOIN sales.customers c ON o.customer_id = c.id WHERE ..."]
```

Query history looks back 30 days. It is available on Databricks, Snowflake, PostgreSQL
(`pg_stat_statements`) and MySQL/MariaDB. Elsewhere, or when access is denied, the tool does not
fail. It returns a one-item list such as
`["<query history not supported for dialect 'sqlite'>"]` or `["<query history unavailable: ...>"]`,
and the agent relies on the other evidence.

---

## `submit_model`

The **terminal tool**. Calling it is the end signal: `ErdAgent` stops the loop and uses the
submission as the result. The model must call it exactly once, when the investigation is done.

**Input** (all four top-level arrays are required):

| Field | Item fields (required in **bold**) |
|---|---|
| `tables` | **`name`** (`schema.table`), **`kind`** (`fact`, `dimension`, `bridge`, `staging`, `other`), **`primary_key`** (list of columns), `grain`, `notes` |
| `relationships` | **`child_table`**, **`child_column`**, **`parent_table`**, **`parent_column`**, **`cardinality`** (`1:1`, `1:N`, `N:M`, written parent:child), **`confidence`** (0..1), **`evidence`**, `declared` (true if the database declares it) |
| `issues` | **`severity`** (`high`, `medium`, `low`), **`description`**, `table` |
| `recommendations` | **`title`**, **`detail`**, `priority` (integer) |

```json
{
  "tables": [
    {"name": "sales.orders", "kind": "fact", "grain": "one row per order", "primary_key": ["order_id"]},
    {"name": "sales.customers", "kind": "dimension", "primary_key": ["id"]}
  ],
  "relationships": [
    {"child_table": "sales.orders", "child_column": "customer_id",
     "parent_table": "sales.customers", "parent_column": "id",
     "cardinality": "1:N", "confidence": 0.99, "declared": false,
     "evidence": "check_join_overlap: 99.6% match, parent column unique"}
  ],
  "issues": [
    {"severity": "high", "table": "sales.orders", "description": "No declared foreign keys"}
  ],
  "recommendations": [
    {"priority": 1, "title": "Declare FKs", "detail": "Add FOREIGN KEY orders.customer_id -> customers.id"}
  ]
}
```

The submission is validated into a `DataModel` (`domain/models.py`). If it is invalid, for
example an unknown `kind` or a `confidence` of 1.5, the model gets the error message back as a
failed tool result and can correct itself and submit again. The agent does not stop until a valid
submission arrives.

---

## How a tool call is executed

```
LLM asks for tool_use(name, input)
        │
        ▼
ErdAgent._execute ──► ToolRegistry.get(name) ──► tool.run(**input)
        │                                              │
        │                                  SchemaRepository (read-only SQL)
        ▼
 JSON result, cut to agent.max_tool_chars  ──► sent back to the LLM
 any exception                             ──► sent back as an error the LLM can react to
 terminal tool (submit_model)              ──► returns the DataModel, loop ends
```

- **Errors never crash the run.** An unknown table, a bad column or a failing query becomes a
  message like `Error: Unknown table 'sales.ordres'; use list_tables`, so the model can fix its
  call.
- **Big results are truncated** to `agent.max_tool_chars` (default 15000, set in `settings.yaml`) to
  protect the model's context window.

## Files in this folder

| File | Role |
|---|---|
| `base.py` | `Tool` base class (`name`, `description`, `input_schema`, `terminal`, `run`) and `DatabaseTool`, which adds a repository |
| `registry.py` | `ToolRegistry`: looks tools up by name and exports their schemas to the LLM. `for_database(repository)` builds the standard set |
| one file per tool | `list_tables.py`, `describe_table.py`, `profile_table.py`, `sample_values.py`, `check_join_overlap.py`, `get_query_joins.py`, `submit_model.py` |

The tool classes are thin. The SQL lives in `database/sqlalchemy_repository.py`.

## Adding a tool

1. Create `my_tool.py` with a subclass of `DatabaseTool` (or `Tool` if it needs no database):

   ```python
   from schema_scout.tools.base import DatabaseTool


   class RowCountTool(DatabaseTool):
       name = "row_count"
       description = "Number of rows in 'schema.table'."
       input_schema = {
           "type": "object",
           "properties": {"table": {"type": "string"}},
           "required": ["table"],
       }

       def run(self, table: str):
           return {"table": table, "rows": self._repo.profile_table(table, 1)["rows"]}
   ```

2. Register it in `ToolRegistry.for_database` in `registry.py`.
3. If it needs new database access, add a method to `SchemaRepository`
   (`database/repository.py`) and implement it in `SqlAlchemyRepository`.
4. Mention it in the system prompt (`agent/prompts.py`) so the model knows when to use it, and add
   it to the table at the top of this file.

Keep these rules: return JSON-serializable data, validate table and column names against the
repository (never build SQL from model-supplied strings), and keep results small.
