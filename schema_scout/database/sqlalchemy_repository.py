import re

import sqlalchemy as sa

from schema_scout.database.client import DatabaseClient
from schema_scout.database.dialects import DialectAdapter, adapter_for
from schema_scout.database.pii_masker import PiiMasker
from schema_scout.database.repository import SchemaRepository
from schema_scout.database.table_ref import TableRef
from schema_scout.domain.models import ColumnInfo


class SqlAlchemyRepository(SchemaRepository):
    """Portable inspection built on SQLAlchemy reflection and Core expressions.

    Table and column names are only ever used after being matched against reflected
    metadata, and are quoted by SQLAlchemy, so model-supplied names cannot inject SQL.
    """

    def __init__(
        self,
        client: DatabaseClient,
        label: str,
        schemas: list[str],
        pii_masker: PiiMasker | None = None,
        adapter: DialectAdapter | None = None,
    ):
        self._client = client
        self.label = label
        self.schemas = schemas
        self.dialect_name = client.dialect_name
        self._pii = pii_masker or PiiMasker()
        self._adapter = adapter or adapter_for(client.dialect_name)
        self._tables: dict[str, dict[str, str]] | None = None  # schema -> name -> type
        self._column_cache: dict[str, list[ColumnInfo]] = {}

    @property
    def known_columns(self) -> dict[str, list[ColumnInfo]]:
        return self._column_cache

    # -- scope & helpers --------------------------------------------------- #
    def _discover(self) -> dict[str, dict[str, str]]:
        if self._tables is None:
            insp = self._client.inspector()
            found: dict[str, dict[str, str]] = {}
            for schema in self.schemas:
                entries = {n: "BASE TABLE" for n in insp.get_table_names(schema=schema)}
                try:
                    entries.update({n: "VIEW" for n in insp.get_view_names(schema=schema)})
                except NotImplementedError:
                    pass
                found[schema] = entries
            self._tables = found
        return self._tables

    def _resolve(self, table: str) -> TableRef:
        ref = TableRef.parse(table)
        if ref.schema not in self.schemas:
            raise ValueError(f"Schema {ref.schema!r} is out of scope")
        if ref.name not in self._discover()[ref.schema]:
            raise ValueError(f"Unknown table {table!r}; use list_tables")
        return ref

    def _columns_of(self, table: str) -> list[ColumnInfo]:
        if table not in self._column_cache:
            self.describe_table(table)
        return self._column_cache[table]

    def _clause(self, table: str) -> sa.TableClause:
        """A lightweight table construct carrying only reflected column names."""
        ref = self._resolve(table)
        cols = [sa.column(c.name) for c in self._columns_of(table)]
        return sa.table(ref.name, *cols, schema=ref.schema)

    @staticmethod
    def _col(clause: sa.TableClause, name: str) -> sa.ColumnClause:
        if name not in clause.c:
            raise ValueError(f"Unknown column {name!r} in {clause.fullname}")
        return clause.c[name]

    def _type_name(self, sa_type) -> str:
        try:
            return sa_type.compile(dialect=self._client.dialect)
        except Exception:
            return str(sa_type)

    # -- inspection -------------------------------------------------------- #
    def list_tables(self) -> list[dict]:
        return [
            {"table_schema": schema, "table_name": name, "table_type": kind}
            for schema, entries in self._discover().items()
            for name, kind in sorted(entries.items())
        ]

    def describe_table(self, table: str) -> dict:
        ref = self._resolve(table)
        insp = self._client.inspector()
        raw = insp.get_columns(ref.name, schema=ref.schema)
        self._column_cache[table] = [ColumnInfo(c["name"], self._type_name(c["type"])) for c in raw]
        return {
            "table": table,
            "comment": self._table_comment(insp, ref),
            "columns": [
                {
                    "column_name": c["name"],
                    "data_type": self._type_name(c["type"]),
                    "is_nullable": c.get("nullable"),
                    "comment": c.get("comment"),
                }
                for c in raw
            ],
            "declared_constraints": self._declared_constraints(insp, ref),
        }

    @staticmethod
    def _table_comment(insp, ref: TableRef) -> str | None:
        try:
            return insp.get_table_comment(ref.name, schema=ref.schema).get("text")
        except Exception:  # not supported by every dialect
            return None

    @staticmethod
    def _declared_constraints(insp, ref: TableRef) -> list[dict]:
        try:
            out: list[dict] = []
            pk = insp.get_pk_constraint(ref.name, schema=ref.schema)
            for col in pk.get("constrained_columns") or []:
                out.append(
                    {
                        "constraint_name": pk.get("name"),
                        "constraint_type": "PRIMARY KEY",
                        "column_name": col,
                    }
                )
            for fk in insp.get_foreign_keys(ref.name, schema=ref.schema):
                for col, ref_col in zip(
                    fk["constrained_columns"], fk["referred_columns"], strict=False
                ):
                    out.append(
                        {
                            "constraint_name": fk.get("name"),
                            "constraint_type": "FOREIGN KEY",
                            "column_name": col,
                            "ref_schema": fk.get("referred_schema") or ref.schema,
                            "ref_table": fk["referred_table"],
                            "ref_column": ref_col,
                        }
                    )
            return out
        except Exception as e:  # constraints are optional on many platforms
            return [{"note": f"could not read constraints: {e}"}]

    def profile_table(self, table: str, max_columns: int = 40) -> dict:
        clause = self._clause(table)
        names = [c.name for c in self._columns_of(table)][:max_columns]
        exprs = [sa.func.count().label("row_count")]
        for i, n in enumerate(names):
            col = clause.c[n]
            exprs.append(sa.func.count(col).label(f"nn_{i}"))
            exprs.append(self._adapter.distinct_count(col).label(f"nd_{i}"))
        row = self._client.fetch(sa.select(*exprs).select_from(clause))[0]
        total = int(row["row_count"])
        profile = []
        for i, n in enumerate(names):
            nn, nd = int(row[f"nn_{i}"]), int(row[f"nd_{i}"])
            profile.append(
                {
                    "column": n,
                    "null_pct": round(100 * (1 - nn / total), 2) if total else None,
                    "approx_distinct": nd,
                    "uniqueness": round(nd / nn, 4) if nn else None,
                }
            )
        return {"table": table, "rows": total, "columns": profile}

    def sample_values(self, table: str, column: str, n: int = 10) -> dict:
        if self._pii.is_pii(column):
            return {"column": column, "values": PiiMasker.PLACEHOLDER}
        n = max(1, min(int(n), 25))
        clause = self._clause(table)
        col = self._col(clause, column)
        rows = self._client.fetch(
            sa.select(col.label("v"))
            .select_from(clause)
            .where(col.is_not(None))
            .distinct()
            .limit(n)
        )
        return {"column": column, "values": [str(r["v"])[:60] for r in rows]}

    def check_join_overlap(
        self,
        child_table: str,
        child_column: str,
        parent_table: str,
        parent_column: str,
        sample_size: int = 50_000,
    ) -> dict:
        sample_size = max(1000, min(int(sample_size), 200_000))
        child_clause, parent_clause = self._clause(child_table), self._clause(parent_table)
        cc = self._col(child_clause, child_column)
        pc = self._col(parent_clause, parent_column)

        child = (
            sa.select(cc.label("k"))
            .select_from(child_clause)
            .where(cc.is_not(None))
            .distinct()
            .limit(sample_size)
            .subquery("child")
        )
        parent = sa.select(pc.label("k")).select_from(parent_clause).subquery("parent")

        stmt = sa.select(
            sa.select(sa.func.count())
            .select_from(child)
            .scalar_subquery()
            .label("child_distinct_sampled"),
            sa.select(sa.func.count())
            .select_from(child)
            .where(child.c.k.in_(sa.select(parent.c.k)))
            .scalar_subquery()
            .label("matched"),
            sa.select(sa.func.count()).select_from(parent).scalar_subquery().label("parent_rows"),
            sa.select(self._adapter.distinct_count(parent.c.k))
            .select_from(parent)
            .scalar_subquery()
            .label("parent_distinct"),
        )
        raw = self._client.fetch(stmt)[0]
        row = {k: int(v or 0) for k, v in raw.items()}
        d = row["child_distinct_sampled"]
        row["match_pct"] = round(100 * row["matched"] / d, 2) if d else None
        row["parent_is_unique"] = (
            row["parent_rows"] > 0 and row["parent_distinct"] >= 0.99 * row["parent_rows"]
        )
        return row

    def get_query_joins(self, limit: int = 40, days: int = 30) -> list[str]:
        """Deduplicated JOIN statements from query history that touch in-scope tables."""
        sql = self._adapter.query_history_sql(days)
        if sql is None:
            return [f"<query history not supported for dialect {self.dialect_name!r}>"]
        try:
            rows = self._client.fetch(sql)
        except Exception as e:
            return [f"<query history unavailable: {e}>"]
        scope = tuple(f"{s.lower()}." for s in self.schemas)
        cap = min(int(limit), 80)
        seen: set[str] = set()
        out: list[str] = []
        for r in rows:
            stmt = re.sub(r"\s+", " ", r["statement_text"] or "").strip()
            if not any(s in stmt.lower() for s in scope):
                continue
            key = re.sub(r"\d+|'[^']*'", "?", stmt)[:300]
            if key in seen:
                continue
            seen.add(key)
            out.append(stmt[:700])
            if len(out) >= cap:
                break
        return out
