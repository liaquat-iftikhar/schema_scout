#!/usr/bin/env python3
"""
ERD Agent for Databricks (Unity Catalog)
----------------------------------------
Claude investigates a catalog through read-only tools, validates candidate
relationships against real data, and submits a structured model. The script
then renders Mermaid + DBML ERDs and a findings report.

Setup:
    pip install anthropic databricks-sql-connector

Env vars:
    ANTHROPIC_API_KEY
    DATABRICKS_SERVER_HOSTNAME   e.g. dbc-xxxx.cloud.databricks.com
    DATABRICKS_HTTP_PATH         SQL warehouse HTTP path
    DATABRICKS_TOKEN             personal access token (use a read-only principal!)
    CLAUDE_MODEL                 optional, default claude-sonnet-5-5

Run:
    python erd_agent.py --catalog main --schemas sales,marketing --interactive
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import anthropic
from databricks import sql

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_TURNS = 60
MAX_TOOL_CHARS = 15_000

IDENT = re.compile(r"^[A-Za-z0-9_]+$")
COLNAME = re.compile(r"^[A-Za-z0-9_ ]+$")
READ_ONLY = re.compile(r"^\s*(select|with|show|describe)\b", re.I)
PII_COLS = re.compile(
    r"(email|phone|ssn|passport|iban|card|password|token|secret|address|birth|dob|"
    r"first_?name|last_?name|full_?name|ip_?addr)",
    re.I,
)


# --------------------------------------------------------------------------- #
# Warehouse access (read-only, validated identifiers)
# --------------------------------------------------------------------------- #
class Warehouse:
    def __init__(self, catalog: str, schemas: list[str]):
        self.catalog = self._ident(catalog)
        self.schemas = [self._ident(s) for s in schemas]
        self.conn = sql.connect(
            server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
            http_path=os.environ["DATABRICKS_HTTP_PATH"],
            access_token=os.environ["DATABRICKS_TOKEN"],
        )
        self.columns: dict[str, list[dict]] = {}  # cache for DBML rendering

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _ident(x: str) -> str:
        if not IDENT.match(x):
            raise ValueError(f"Invalid identifier: {x!r}")
        return x

    @staticmethod
    def _col(x: str) -> str:
        if not COLNAME.match(x):
            raise ValueError(f"Invalid column name: {x!r}")
        return f"`{x}`"

    def _fq(self, table: str) -> str:
        parts = table.split(".")
        if len(parts) != 2:
            raise ValueError("Use 'schema.table' format")
        schema, name = parts
        if schema not in self.schemas:
            raise ValueError(f"Schema {schema!r} is out of scope")
        return f"`{self.catalog}`.`{self._ident(schema)}`.`{self._ident(name)}`"

    def query(self, statement: str) -> list[dict]:
        if not READ_ONLY.match(statement) or ";" in statement.strip().rstrip(";"):
            raise PermissionError("Only single read-only statements are allowed")
        with self.conn.cursor() as cur:
            cur.execute(statement)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _schema_list(self) -> str:
        return ",".join(f"'{s}'" for s in self.schemas)

    # -- tools ------------------------------------------------------------- #
    def list_tables(self) -> list[dict]:
        return self.query(
            f"SELECT table_schema, table_name, table_type, comment "
            f"FROM `{self.catalog}`.information_schema.tables "
            f"WHERE table_schema IN ({self._schema_list()}) "
            f"ORDER BY table_schema, table_name"
        )

    def describe_table(self, table: str) -> dict:
        schema, name = table.split(".")
        self._fq(table)  # validation
        cols = self.query(
            f"SELECT column_name, data_type, is_nullable, comment "
            f"FROM `{self.catalog}`.information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{name}' "
            f"ORDER BY ordinal_position"
        )
        self.columns[table] = [{"name": c["column_name"], "type": c["data_type"]} for c in cols]
        try:
            constraints = self.query(
                f"SELECT tc.constraint_name, tc.constraint_type, kcu.column_name, "
                f"       ccu.table_schema AS ref_schema, ccu.table_name AS ref_table, "
                f"       ccu.column_name AS ref_column "
                f"FROM `{self.catalog}`.information_schema.table_constraints tc "
                f"JOIN `{self.catalog}`.information_schema.key_column_usage kcu "
                f"  ON tc.constraint_name = kcu.constraint_name "
                f" AND tc.table_schema = kcu.table_schema "
                f" AND tc.table_name = kcu.table_name "
                f"LEFT JOIN `{self.catalog}`.information_schema.constraint_column_usage ccu "
                f"  ON tc.constraint_name = ccu.constraint_name "
                f" AND tc.constraint_type = 'FOREIGN KEY' "
                f"WHERE tc.table_schema = '{schema}' AND tc.table_name = '{name}'"
            )
        except Exception as e:  # constraints are optional in Databricks
            constraints = [{"note": f"could not read constraints: {e}"}]
        return {"table": table, "columns": cols, "declared_constraints": constraints}

    def profile_table(self, table: str, max_columns: int = 40) -> dict:
        fq = self._fq(table)
        cols = self.columns.get(table) or self.describe_table(table)["columns"]
        names = [c["name"] if "name" in c else c["column_name"] for c in cols][:max_columns]
        exprs = ["COUNT(*) AS `__rows`"]
        for i, n in enumerate(names):
            c = self._col(n)
            exprs.append(f"COUNT({c}) AS `nn_{i}`")
            exprs.append(f"approx_count_distinct({c}) AS `nd_{i}`")
        row = self.query(f"SELECT {', '.join(exprs)} FROM {fq}")[0]
        total = row["__rows"]
        profile = []
        for i, n in enumerate(names):
            nn, nd = row[f"nn_{i}"], row[f"nd_{i}"]
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
        if PII_COLS.search(column):
            return {"column": column, "values": "<masked: looks like PII>"}
        n = max(1, min(int(n), 25))
        rows = self.query(
            f"SELECT DISTINCT {self._col(column)} AS v FROM {self._fq(table)} "
            f"WHERE {self._col(column)} IS NOT NULL LIMIT {n}"
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
        c, p = self._col(child_column), self._col(parent_column)
        row = self.query(
            f"WITH child AS (SELECT DISTINCT {c} AS k FROM {self._fq(child_table)} "
            f"               WHERE {c} IS NOT NULL LIMIT {sample_size}), "
            f"parent AS (SELECT {p} AS k FROM {self._fq(parent_table)}) "
            f"SELECT (SELECT COUNT(*) FROM child) AS child_distinct_sampled, "
            f"       (SELECT COUNT(*) FROM child WHERE k IN (SELECT k FROM parent)) AS matched, "
            f"       (SELECT COUNT(*) FROM parent) AS parent_rows, "
            f"       (SELECT approx_count_distinct(k) FROM parent) AS parent_distinct"
        )[0]
        d = row["child_distinct_sampled"] or 0
        row["match_pct"] = round(100 * row["matched"] / d, 2) if d else None
        row["parent_is_unique"] = (
            row["parent_rows"] > 0 and row["parent_distinct"] >= 0.99 * row["parent_rows"]
        )
        return row

    def get_query_joins(self, limit: int = 40, days: int = 30) -> list[str]:
        """Return deduplicated JOIN statements from query history that touch in-scope tables."""
        try:
            rows = self.query(
                f"SELECT statement_text FROM system.query.history "
                f"WHERE execution_status = 'FINISHED' "
                f"AND start_time >= current_date() - INTERVAL {int(days)} DAYS "
                f"AND lower(statement_text) LIKE '%join%' "
                f"LIMIT 3000"
            )
        except Exception as e:
            return [f"<query history unavailable: {e}>"]
        scope = tuple(f"{s}." for s in self.schemas)
        seen, out = set(), []
        for r in rows:
            stmt = re.sub(r"\s+", " ", r["statement_text"] or "").strip()
            if not any(s in stmt for s in scope):
                continue
            key = re.sub(r"\d+|'[^']*'", "?", stmt)[:300]
            if key in seen:
                continue
            seen.add(key)
            out.append(stmt[:700])
            if len(out) >= min(int(limit), 80):
                break
        return out


# --------------------------------------------------------------------------- #
# Tool definitions for Claude
# --------------------------------------------------------------------------- #
TOOLS = [
    {
        "name": "list_tables",
        "description": "List all tables/views in the in-scope schemas.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_table",
        "description": "Columns, types, comments and declared PK/FK constraints for 'schema.table'.",
        "input_schema": {
            "type": "object",
            "properties": {"table": {"type": "string"}},
            "required": ["table"],
        },
    },
    {
        "name": "profile_table",
        "description": "Row count plus null % and approximate distinct counts per column. Use to find primary key candidates and grain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string"},
                "max_columns": {"type": "integer", "default": 40},
            },
            "required": ["table"],
        },
    },
    {
        "name": "sample_values",
        "description": "A few distinct values of a column (PII-looking columns are masked).",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string"},
                "column": {"type": "string"},
                "n": {"type": "integer", "default": 10},
            },
            "required": ["table", "column"],
        },
    },
    {
        "name": "check_join_overlap",
        "description": "Validate a candidate FK: share of distinct child values found in the parent column, and whether the parent column is unique.",
        "input_schema": {
            "type": "object",
            "properties": {
                "child_table": {"type": "string"},
                "child_column": {"type": "string"},
                "parent_table": {"type": "string"},
                "parent_column": {"type": "string"},
                "sample_size": {"type": "integer", "default": 50000},
            },
            "required": ["child_table", "child_column", "parent_table", "parent_column"],
        },
    },
    {
        "name": "get_query_joins",
        "description": "Real JOIN statements from recent query history touching in-scope tables. Strong evidence of true relationships.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 40}},
        },
    },
    {
        "name": "submit_model",
        "description": "Submit the final data model. Call exactly once, when investigation is complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tables": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "schema.table"},
                            "kind": {
                                "type": "string",
                                "enum": ["fact", "dimension", "bridge", "staging", "other"],
                            },
                            "grain": {"type": "string"},
                            "primary_key": {"type": "array", "items": {"type": "string"}},
                            "notes": {"type": "string"},
                        },
                        "required": ["name", "kind", "primary_key"],
                    },
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "child_table": {"type": "string"},
                            "child_column": {"type": "string"},
                            "parent_table": {"type": "string"},
                            "parent_column": {"type": "string"},
                            "cardinality": {
                                "type": "string",
                                "enum": ["1:1", "1:N", "N:M"],
                                "description": "parent:child",
                            },
                            "confidence": {"type": "number", "description": "0..1"},
                            "declared": {"type": "boolean"},
                            "evidence": {"type": "string"},
                        },
                        "required": [
                            "child_table",
                            "child_column",
                            "parent_table",
                            "parent_column",
                            "cardinality",
                            "confidence",
                            "evidence",
                        ],
                    },
                },
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                            "table": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["severity", "description"],
                    },
                },
                "recommendations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "priority": {"type": "integer"},
                            "title": {"type": "string"},
                            "detail": {"type": "string"},
                        },
                        "required": ["title", "detail"],
                    },
                },
            },
            "required": ["tables", "relationships", "issues", "recommendations"],
        },
    },
]

SYSTEM = """You are a senior data modeler. Reverse-engineer an accurate ERD for a \
Databricks catalog and propose optimizations.

Workflow:
1. list_tables, then describe_table for every table (declared constraints first).
2. profile_table to find primary-key candidates (uniqueness ~1.0, low nulls) and grain.
3. get_query_joins to see how tables are really joined.
4. Build candidate relationships from declared FKs, query-history joins, and \
naming patterns (customer_id -> dim_customer.id / customer_key), including \
suffix/prefix variants. Types must be compatible.
5. VALIDATE every non-declared candidate with check_join_overlap. Accept at \
>=95% match with a unique parent column; flag 80-95% as low confidence \
(orphans); drop below 80% unless query history strongly supports it.
6. Classify tables (fact / dimension / bridge / staging), state the grain.
7. Look for optimization issues: no usable key, duplicated or near-duplicate \
tables, over-wide denormalized tables, N:M relations lacking a bridge, \
inconsistent key naming/types, orphaned tables, undeclared constraints, and \
tables that should be conformed dimensions. Recommend concrete changes \
(target star schema, declare PK/FK informational constraints, liquid \
clustering / partition keys based on join and filter patterns).
8. Call submit_model once.

Rules: be efficient (batch independent tool calls in one turn), never invent \
relationships without evidence, and cite evidence (overlap %, query example, \
declared constraint) for each relationship. Direction: the child holds the FK; \
cardinality is written parent:child."""


# --------------------------------------------------------------------------- #
# Agent loop
# --------------------------------------------------------------------------- #
def run_agent(wh: Warehouse) -> dict:
    client = anthropic.Anthropic()
    dispatch = {
        "list_tables": lambda **_: wh.list_tables(),
        "describe_table": wh.describe_table,
        "profile_table": wh.profile_table,
        "sample_values": wh.sample_values,
        "check_join_overlap": wh.check_join_overlap,
        "get_query_joins": wh.get_query_joins,
    }
    messages = [
        {
            "role": "user",
            "content": f"Analyze catalog `{wh.catalog}`, schemas: {', '.join(wh.schemas)}. "
            f"Build and optimize the ERD.",
        }
    ]

    for turn in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL, max_tokens=8000, system=SYSTEM, tools=TOOLS, messages=messages
        )
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            messages.append(
                {"role": "user", "content": "Finish by calling submit_model with your findings."}
            )
            continue

        results = []
        for tu in tool_uses:
            if tu.name == "submit_model":
                print(f"[turn {turn}] model submitted")
                return tu.input
            print(f"[turn {turn}] {tu.name}({json.dumps(tu.input)[:120]})")
            try:
                out = dispatch[tu.name](**tu.input)
                text = json.dumps(out, default=str)[:MAX_TOOL_CHARS]
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": text})
            except Exception as e:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"Error: {e}",
                        "is_error": True,
                    }
                )
        messages.append({"role": "user", "content": results})

    raise RuntimeError("Agent did not submit a model within the turn limit")


# --------------------------------------------------------------------------- #
# Human review of low-confidence relationships
# --------------------------------------------------------------------------- #
def review(model: dict, threshold: float) -> dict:
    kept = []
    for r in model["relationships"]:
        if r["confidence"] >= threshold or r.get("declared"):
            kept.append(r)
            continue
        print(
            f"\n? {r['child_table']}.{r['child_column']} -> "
            f"{r['parent_table']}.{r['parent_column']}  [{r['cardinality']}, "
            f"confidence {r['confidence']:.2f}]\n  evidence: {r['evidence']}"
        )
        if input("  keep this relationship? [y/N] ").strip().lower() == "y":
            kept.append(r)
    model["relationships"] = kept
    return model


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def _m(name: str) -> str:
    return re.sub(r"\W", "_", name)


def to_mermaid(model: dict) -> str:
    pk = {t["name"]: set(t["primary_key"]) for t in model["tables"]}
    fk: dict[str, set] = {}
    for r in model["relationships"]:
        fk.setdefault(r["child_table"], set()).add(r["child_column"])
    sym = {"1:N": "||--o{", "1:1": "||--||", "N:M": "}o--o{"}

    lines = ["erDiagram"]
    for t in model["tables"]:
        lines.append(f"  {_m(t['name'])} {{")
        for col in sorted(pk[t["name"]] | fk.get(t["name"], set())):
            tags = []
            if col in pk[t["name"]]:
                tags.append("PK")
            if col in fk.get(t["name"], set()):
                tags.append("FK")
            lines.append(f"    string {_m(col)} {','.join(tags)}")
        lines.append("  }")
    for r in model["relationships"]:
        lines.append(
            f"  {_m(r['parent_table'])} {sym[r['cardinality']]} {_m(r['child_table'])} "
            f': "{r["child_column"]}"'
        )
    return "\n".join(lines) + "\n"


def to_dbml(model: dict, wh: Warehouse) -> str:
    out = []
    for t in model["tables"]:
        pk = set(t["primary_key"])
        out.append(f"Table {t['name']} {{")
        cols = wh.columns.get(t["name"], [])
        for c in cols:
            ty = re.sub(r"[^A-Za-z0-9_()]", "_", c["type"])
            col = c["name"] if re.match(r"^\w+$", c["name"]) else f'"{c["name"]}"'
            out.append(f"  {col} {ty}" + (" [pk]" if c["name"] in pk else ""))
        if t.get("grain"):
            out.append(f"  Note: 'kind={t['kind']}; grain={t['grain']}'".replace('"', ""))
        out.append("}\n")
    sym = {"1:N": "<", "1:1": "-", "N:M": "<>"}
    for r in model["relationships"]:
        out.append(
            f"Ref: {r['parent_table']}.{r['parent_column']} {sym[r['cardinality']]} "
            f"{r['child_table']}.{r['child_column']}"
        )
    return "\n".join(out) + "\n"


def to_report(model: dict, catalog: str) -> str:
    L = [
        f"# Data model report: `{catalog}`\n",
        "## Tables\n",
        "| Table | Kind | Grain | Primary key |",
        "|---|---|---|---|",
    ]
    for t in model["tables"]:
        L.append(
            f"| {t['name']} | {t['kind']} | {t.get('grain', '')} | {', '.join(t['primary_key'])} |"
        )
    L += [
        "\n## Relationships\n",
        "| Child | Parent | Cardinality | Confidence | Evidence |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(model["relationships"], key=lambda r: -r["confidence"]):
        L.append(
            f"| {r['child_table']}.{r['child_column']} | {r['parent_table']}.{r['parent_column']} "
            f"| {r['cardinality']} | {r['confidence']:.2f} | {r['evidence']} |"
        )
    L.append("\n## Issues\n")
    order = {"high": 0, "medium": 1, "low": 2}
    for i in sorted(model["issues"], key=lambda i: order[i["severity"]]):
        L.append(f"- **{i['severity'].upper()}** {i.get('table', '')}: {i['description']}")
    L.append("\n## Recommendations\n")
    for n, rec in enumerate(
        sorted(model["recommendations"], key=lambda r: r.get("priority", 99)), 1
    ):
        L.append(f"{n}. **{rec['title']}**: {rec['detail']}")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schemas", required=True, help="comma-separated")
    ap.add_argument("--out", default="erd_output")
    ap.add_argument(
        "--interactive", action="store_true", help="review low-confidence relationships"
    )
    ap.add_argument("--threshold", type=float, default=0.85)
    args = ap.parse_args()

    wh = Warehouse(args.catalog, [s.strip() for s in args.schemas.split(",")])
    model = run_agent(wh)
    if args.interactive:
        model = review(model, args.threshold)

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    (out / "model.json").write_text(json.dumps(model, indent=2))
    (out / "erd.mmd").write_text(to_mermaid(model))
    (out / "erd.dbml").write_text(to_dbml(model, wh))
    (out / "report.md").write_text(to_report(model, args.catalog))
    print(f"\nDone. Files written to {out}/  (erd.mmd, erd.dbml, report.md, model.json)")


if __name__ == "__main__":
    sys.exit(main())
