# Schema Scout

Schema Scout reverse-engineers an entity-relationship diagram (ERD) from a database or data
warehouse that has few or no declared foreign keys.

An LLM agent investigates the database through a small set of **read-only tools**. It reads table
structure, profiles columns, samples values, and tests candidate relationships against the real
data (for example, "do 98% of `orders.customer_id` values exist in `customers.id`?"). It then
submits a structured model, and Schema Scout renders that model into:

| File | Contents |
|---|---|
| `model.json` | the full model: tables, relationships with confidence and evidence, issues, recommendations |
| `erd.mmd` | Mermaid ER diagram |
| `erd.dbml` | DBML (paste into dbdiagram.io) |
| `report.md` | findings report: data-quality issues and recommended fixes |

**Highlights**

- **Any SQL database or warehouse** with a SQLAlchemy dialect: PostgreSQL, MySQL/MariaDB, SQL Server,
  Oracle, SQLite, Snowflake, BigQuery, Redshift, Databricks and more.
- **Any LLM** that supports tool calling: Anthropic or OpenAI (and OpenAI-compatible servers such as
  Ollama and vLLM).
- **Safe by design:** only read-only SQL, table and column names are validated against the real
  schema, likely-PII columns are never sampled, and credentials can only come from environment
  variables.
- **Configurable per environment** (`local`, `production`) with Dynaconf and YAML.

## How it works

```
 CLI ──► SchemaScoutApp ──► ErdAgent ◄──► LlmClient (Anthropic / OpenAI)
                               │
                               ▼
                         ToolRegistry ──► SchemaRepository ──► database (read-only)
                               │
                         submit_model  ── end signal, returns a DataModel
                               ▼
              [optional human review] ──► ArtifactWriter ──► model.json, erd.mmd, erd.dbml, report.md
```

1. The agent sends the task and the tool definitions to the LLM.
2. The LLM calls tools (`list_tables`, `describe_table`, `profile_table`, `sample_values`,
   `check_join_overlap`, `get_query_joins`). Schema Scout runs them and returns the results.
   Each tool's inputs and outputs are documented in [Agent tools](schema_scout/tools/README.md).
3. The loop continues until the LLM calls `submit_model`. That call is the end signal.
4. With `--interactive`, a human confirms low-confidence relationships.
5. Renderers write the output files.

## Folder structure

```
schema-scout/
├── schema_scout/                  the application package
│   ├── cli.py                     argument parsing only
│   ├── app.py                     composition root: wires config, DB, LLM, agent, renderers
│   ├── settings.py                Dynaconf loader (environments, layering, credential guard)
│   ├── config.py                  typed DatabaseConfig / LlmConfig / AgentConfig
│   ├── domain/models.py           DataModel, Table, Relationship, Issue, Recommendation, enums
│   ├── database/                  see database/README.md
│   │   ├── client.py              DatabaseClient: engine, inspector, guarded fetch
│   │   ├── repository.py          SchemaRepository interface (what the tools need)
│   │   ├── sqlalchemy_repository.py   portable implementation of that interface
│   │   ├── dialects/              per-platform adapters (Databricks, Snowflake, ...) + registry
│   │   ├── sql_guard.py           rejects anything but read-only statements
│   │   ├── table_ref.py           schema.table value object
│   │   └── pii_masker.py          detects PII columns so values are never sampled
│   ├── tools/                     one class per agent tool + ToolRegistry (see tools/README.md)
│   ├── llm/                       LlmClient interface, neutral Message types,
│   │                              Anthropic and OpenAI clients, factory
│   ├── agent/                     ErdAgent (the tool-use loop) and prompts
│   ├── renderers/                 Mermaid, DBML and report renderers
│   └── output/                    ArtifactWriter, RelationshipReviewer (human review)
├── tests/                         pytest suite (SQLite end-to-end, fake LLM for the agent loop)
├── settings.yaml                  non-secret configuration, one section per environment
├── .env.example                   template for credentials (copy to .env, never commit)
├── pyproject.toml                 package metadata, dependencies, ruff and pytest config
├── requirements.txt               pip-installable dependency list
├── Dockerfile                     multi-stage, non-root production image
├── Makefile                       setup / lint / format / test / check / docker shortcuts
├── .github/workflows/ci.yml       CI: lint, test matrix, Docker build and publish
├── .github/dependabot.yml         dependency update automation
└── erd_agent.py                   legacy single-file original; superseded, safe to delete
```

**Where to start reading:** `cli.py` → `app.py` → `agent/erd_agent.py` → `tools/` →
`database/sqlalchemy_repository.py`. The tools are documented in
[`schema_scout/tools/README.md`](schema_scout/tools/README.md).

## Setup locally

**Requirements:** Python 3.10 or newer, read access to a database, and an API key for an LLM
provider.

```bash
# 1. Create a virtual environment and install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,anthropic,postgres]"     # pick one LLM extra and your DB driver extra(s)
#   or: make setup EXTRAS="dev,anthropic,databricks"
#   or: pip install -r requirements.txt && pip install -e .

# 2. Describe your database in settings.yaml (host, port, database, username: no password)
#    Edit the `local:` section.

# 3. Provide credentials as environment variables
cp .env.example .env            # then fill in the values; .env is gitignored
#   SCHEMA_SCOUT_DATABASE__PASSWORD=...
#   ANTHROPIC_API_KEY=...        (or OPENAI_API_KEY, matching llm.provider)

# 4. Run
python -m schema_scout --schemas public,sales --interactive
```

Outputs go to `erd_output/` by default (change with `--out`).

Database driver extras: `postgres`, `mysql`, `snowflake`, `bigquery`, `databricks`, `redshift`,
`mssql`, `oracle`. LLM extras: `anthropic`, `openai`.

### Command-line options

| Option | Meaning |
|---|---|
| `--schemas a,b` | **Required.** Schemas to analyze. For MySQL this is the database name; SQLite uses `main`. |
| `--catalog NAME` | Optional label for the report. On Databricks it also selects the catalog. |
| `--out DIR` | Output directory (default `erd_output`). |
| `--interactive` | Ask for confirmation of low-confidence relationships. |
| `--threshold 0.85` | Confidence below which relationships are reviewed. |
| `--env NAME` | `local` or `production` (else `SCHEMA_SCOUT_ENV`, else `local`). |
| `--config PATH` | Extra settings file, repeatable. Same layout, same no-credentials rule. |

## Configuration

**Connection details live in `settings.yaml`. Credentials live only in environment variables.**

| Where | What |
|---|---|
| `settings.yaml` (committed) | per environment: `database` (drivername, host, port, database, username, query), `llm` (provider, model, max_tokens), `agent` (max_turns, max_tool_chars) |
| environment variables or `.env` (gitignored) | `SCHEMA_SCOUT_DATABASE__PASSWORD`, and the LLM key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `SCHEMA_SCOUT_LLM__API_KEY`) |

The loader refuses to start if a settings file contains `password`, `api_key`, `token` or
`secret` with a value, so credentials cannot be committed by accident.

`settings.yaml` has a `default:` section plus `local:` and `production:`. `default` is always
loaded, and the selected environment is merged over it key by key.

```yaml
production:
  database:                     # becomes drivername://username:<password>@host:port/database?query
    drivername: postgresql+psycopg2
    host: prod-db.example.com
    port: 5432
    database: analytics
    username: readonly          # use a read-only database user
    # query: {sslmode: require}  # driver options, e.g. Snowflake warehouse/role, Databricks http_path/catalog
  agent:
    max_turns: 60               # optional guard rail
```

Sources, later wins:

1. `settings.yaml` (found in the working directory or a parent)
2. files passed with `--config PATH`
3. `.env`
4. environment variables prefixed `SCHEMA_SCOUT_`, with `__` for nesting
   (for example `SCHEMA_SCOUT_DATABASE__HOST`, `SCHEMA_SCOUT_LLM__MODEL`)

### Platform examples

| Platform | `drivername` | Notes |
|---|---|---|
| PostgreSQL / Redshift | `postgresql+psycopg2` | host, port, database, username |
| MySQL / MariaDB | `mysql+pymysql` | `database` is the schema |
| Snowflake | `snowflake` | `host: <account>`, `database: <db>/<schema>`, `query: {warehouse: WH, role: READONLY}` |
| Databricks | `databricks` | `host`, `username: token`, `query: {http_path: /sql/1.0/warehouses/xxxx, catalog: main}`; password is the access token |
| BigQuery | `bigquery` | `host: <project>`, `database: <dataset>` |
| SQLite | `sqlite` | `database: path/to/file.db`; schema is `main` |

Full examples for every platform (plus Redshift, SQL Server and Oracle), driver extras and the
permissions the database user needs are in
[`schema_scout/database/README.md`](schema_scout/database/README.md).

### Choosing the LLM

```yaml
llm:
  provider: anthropic        # anthropic | openai
  model: claude-sonnet-5-5
  max_tokens: 8000
  # base_url: http://localhost:11434/v1   # any OpenAI-compatible server, with provider: openai
```

Override from the environment, for example
`SCHEMA_SCOUT_LLM__PROVIDER=openai SCHEMA_SCOUT_LLM__MODEL=gpt-4o`. The model must support tool
calling. To add a provider, subclass `LlmClient` in `llm/` and register it in `llm/factory.py`.

### When the agent stops

The agent runs until the model calls `submit_model`. By default there is no turn limit. Set
`agent.max_turns` (or `SCHEMA_SCOUT_AGENT__MAX_TURNS=60`) to add a guard rail: the run then fails
with an error if the limit is reached first. Separately, if the model ends its turn three times in
a row without calling `submit_model`, the run stops with an error.

## Deploy to production

Production runs the same code with `--env production` (the Docker image sets this by default). The
steps are the same wherever you host it:

1. **Create a read-only database user** for Schema Scout.
2. **Fill in the `production:` block of `settings.yaml`** (host, port, database, username,
   `max_turns`). Commit it. It holds no secrets.
3. **Store the secrets in your secret manager** (GitHub/GitLab secrets, AWS Secrets Manager,
   Vault, Kubernetes Secrets, ...): the database password and the LLM API key.
4. **Run the container** with the secrets injected as environment variables.

### Build and run the Docker image

```bash
# Pick the LLM and database extras baked into the image
docker build --build-arg EXTRAS=anthropic,postgres -t schema-scout .

docker run --rm \
  -e SCHEMA_SCOUT_DATABASE__PASSWORD \
  -e ANTHROPIC_API_KEY \
  -v "$PWD/erd_output:/app/erd_output" \
  schema-scout --schemas public,sales
```

The image is multi-stage, runs as a non-root user, and contains `settings.yaml` but no
credentials. Any setting can be overridden at runtime without rebuilding, for example
`-e SCHEMA_SCOUT_DATABASE__HOST=other-host` or `-e SCHEMA_SCOUT_AGENT__MAX_TURNS=40`. Results are
written to `/app/erd_output`, so mount a volume there.

### CI/CD (GitHub Actions)

`.github/workflows/ci.yml` runs on pull requests and on pushes to `main` and `v*` tags:

| Job | What it does |
|---|---|
| `lint` | `ruff check` and `ruff format --check` |
| `test` | `pytest` on Python 3.10 to 3.13 |
| `docker` | after lint and test pass: builds the image, smoke-tests `--help`, and pushes to `ghcr.io/<owner>/<repo>` from `main` and version tags only, never from pull requests |

**Release:** `git tag v0.1.0 && git push --tags` publishes the image as `0.1.0`, `0.1` and the
commit SHA. Then deploy that tag to your platform.

The image's default extras are `anthropic,databricks`. To publish an image for another database,
change `ARG EXTRAS` in the `Dockerfile`.

### Running on a schedule

Schema Scout is a batch job, not a server. Run the container from whatever scheduler you use
(Kubernetes `CronJob`, ECS scheduled task, Airflow, cron) and collect `/app/erd_output`, for
example by mounting a volume or syncing it to object storage.

## Platform support

Metadata (tables, views, columns, PK/FK) comes from SQLAlchemy reflection, and the profiling and
join-overlap queries are built with SQLAlchemy Core, so they work on every dialect. Adapters in
`database/dialects/` refine two things:

| Feature | Default | Platform-specific |
|---|---|---|
| Distinct counts | exact `COUNT(DISTINCT)` | `approx_count_distinct` on Databricks, Snowflake, BigQuery |
| Query-history join mining | unsupported (the agent falls back to other evidence) | Databricks, Snowflake, PostgreSQL (`pg_stat_statements`), MySQL/MariaDB |

To support another platform, add a `DialectAdapter` subclass and register it in
`dialects/registry.py`. See [`schema_scout/database/README.md`](schema_scout/database/README.md#adding-or-customising-a-dialect).

## Development

```bash
make setup      # venv + editable install (EXTRAS="dev,openai,mysql" to change)
make check      # ruff lint + format check + tests (what CI runs)
make format     # auto-fix lint and formatting
pytest          # tests only
```

- **Add a tool:** subclass `Tool` (or `DatabaseTool`) in `tools/` and register it in
  `ToolRegistry.for_database`. Step-by-step in
  [`schema_scout/tools/README.md`](schema_scout/tools/README.md#adding-a-tool).
- **Add an output format:** subclass `Renderer` and add it in `app.py`.
- **Add an LLM provider:** see "Choosing the LLM".
- **Add a database platform:** install its SQLAlchemy driver; add a `DialectAdapter` only if you
  want approximate counts or query-history mining. Details in
  [`schema_scout/database/README.md`](schema_scout/database/README.md).

Dependabot keeps GitHub Actions, pip and Docker dependencies current.
