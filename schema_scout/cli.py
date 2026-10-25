import argparse
from pathlib import Path

from schema_scout.app import RunOptions, SchemaScoutApp
from schema_scout.config import AgentConfig, ConfigError, DatabaseConfig, LlmConfig
from schema_scout.settings import KNOWN_ENVS, build_settings


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="schema-scout",
        description="Reverse-engineer an ERD from any SQLAlchemy-supported database or warehouse with Claude.",
    )
    ap.add_argument(
        "--catalog",
        help="catalog/database name: labels the report, and selects the catalog for Databricks "
        "when connecting via DATABRICKS_* variables",
    )
    ap.add_argument("--schemas", required=True, help="comma-separated schemas to analyze")
    ap.add_argument("--out", default="erd_output", type=Path)
    ap.add_argument(
        "--interactive", action="store_true", help="review low-confidence relationships"
    )
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument(
        "--env",
        choices=KNOWN_ENVS,
        help="settings environment (default: $SCHEMA_SCOUT_ENV, else local)",
    )
    ap.add_argument(
        "--config",
        type=Path,
        action="append",
        help="extra settings file (yaml/toml/json); repeatable",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    options = RunOptions(
        label=args.catalog,
        schemas=[s.strip() for s in args.schemas.split(",") if s.strip()],
        out_dir=args.out,
        interactive=args.interactive,
        threshold=args.threshold,
    )
    try:
        settings = build_settings(args.config, args.env)
        app = SchemaScoutApp(
            DatabaseConfig.from_settings(settings, args.catalog),
            LlmConfig.from_settings(settings),
            AgentConfig.from_settings(settings),
        )
    except (ConfigError, ValueError) as e:
        print(f"error: {e}")
        return 2

    print(f"environment: {settings.current_env.lower()}")
    try:
        written = app.run(options)
    except ConfigError as e:
        print(f"error: {e}")
        return 2
    print(f"\nDone. Files written to {options.out_dir}/  ({', '.join(written)})")
    return 0
