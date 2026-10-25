import pytest
from dynaconf.validator import ValidationError

from schema_scout.config import AgentConfig, ConfigError, DatabaseConfig, LlmConfig
from schema_scout.settings import SecretInFileError, build_settings

FILE = """
default:
  llm:
    model: from-default
    provider: openai
  agent:
    max_turns: 5
local:
  database:
    drivername: sqlite
    database: local.db
  llm:
    model: from-local
production:
  database:
    drivername: postgresql+psycopg2
    host: prod-host
    port: 5432
    database: analytics
    username: readonly
    query:
      sslmode: require
  agent:
    max_turns: 99
"""


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no stray settings.yaml / .env from the repo
    monkeypatch.delenv("SCHEMA_SCOUT_ENV", raising=False)
    return tmp_path


@pytest.fixture
def cfg_file(isolated):
    f = isolated / "extra.yaml"
    f.write_text(FILE)
    return f


def test_defaults_when_nothing_configured():
    s = build_settings()
    assert AgentConfig.from_settings(s) == AgentConfig()
    assert LlmConfig.from_settings(s) == LlmConfig()


def test_missing_database_raises():
    with pytest.raises(ConfigError):
        DatabaseConfig.from_settings(build_settings())


def test_local_is_default_environment(cfg_file):
    s = build_settings([cfg_file])
    assert s.current_env.lower() == "local"
    assert (LlmConfig.from_settings(s).model, LlmConfig.from_settings(s).provider) == (
        "from-local",
        "openai",
    )
    assert AgentConfig.from_settings(s).max_turns == 5  # env overrides one key, keeps the rest
    assert DatabaseConfig.from_settings(s).url.render_as_string() == "sqlite:///local.db"


def test_production_via_argument(cfg_file):
    s = build_settings([cfg_file], env="production")
    assert LlmConfig.from_settings(s).model == "from-default"
    assert AgentConfig.from_settings(s).max_turns == 99
    url = DatabaseConfig.from_settings(s).url
    assert (url.drivername, url.host, url.port, url.database, url.username) == (
        "postgresql+psycopg2",
        "prod-host",
        5432,
        "analytics",
        "readonly",
    )
    assert url.query == {"sslmode": "require"}
    assert url.password is None


def test_production_via_env_var_and_argument_wins(cfg_file, monkeypatch):
    monkeypatch.setenv("SCHEMA_SCOUT_ENV", "production")
    assert build_settings([cfg_file]).current_env.lower() == "production"
    assert build_settings([cfg_file], env="local").current_env.lower() == "local"


def test_unknown_environment_rejected():
    with pytest.raises(ValueError):
        build_settings(env="staging")


def test_env_vars_override_environment_files(cfg_file, monkeypatch):
    monkeypatch.setenv("SCHEMA_SCOUT_LLM__MODEL", "from-env-var")
    monkeypatch.setenv("SCHEMA_SCOUT_DATABASE__HOST", "other-host")
    s = build_settings([cfg_file], env="production")
    assert LlmConfig.from_settings(s).model == "from-env-var"
    assert AgentConfig.from_settings(s).max_turns == 99
    assert DatabaseConfig.from_settings(s).url.host == "other-host"


def test_password_comes_from_environment_only(cfg_file, monkeypatch):
    monkeypatch.setenv("SCHEMA_SCOUT_DATABASE__PASSWORD", "s3cret")
    url = DatabaseConfig.from_settings(build_settings([cfg_file], env="production")).url
    assert url.password == "s3cret"
    assert "s3cret" not in repr(url) and "s3cret" not in url.render_as_string()


def test_databricks_catalog_from_cli(isolated):
    f = isolated / "dbx.yaml"
    f.write_text(
        "default:\n  database:\n    drivername: databricks\n    host: h.cloud.databricks.com\n"
        "    username: token\n    query:\n      http_path: /sql/1.0/warehouses/x\n"
    )
    url = DatabaseConfig.from_settings(build_settings([f]), catalog="main").url
    assert url.drivername == "databricks"
    assert url.query == {"http_path": "/sql/1.0/warehouses/x", "catalog": "main"}


@pytest.mark.parametrize(
    "body",
    [
        "default:\n  database:\n    password: hunter2\n",
        "production:\n  llm:\n    api_key: sk-abc\n",
        "default:\n  databricks:\n    token: dapi123\n",
    ],
)
def test_credentials_in_a_file_are_rejected(isolated, body):
    f = isolated / "bad.yaml"
    f.write_text(body)
    with pytest.raises(SecretInFileError):
        build_settings([f])


def test_empty_secret_placeholders_are_allowed(isolated):
    f = isolated / "ok.yaml"
    f.write_text("default:\n  database:\n    password:\n")
    build_settings([f])


def test_settings_yaml_found_in_parent_directory(isolated, monkeypatch):
    (isolated / "settings.yaml").write_text("default:\n  llm:\n    model: from-parent\n")
    sub = isolated / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert LlmConfig.from_settings(build_settings()).model == "from-parent"


def test_invalid_value_rejected(monkeypatch):
    monkeypatch.setenv("SCHEMA_SCOUT_LLM__MAX_TOKENS", "0")
    with pytest.raises(ValidationError):
        build_settings()


def test_llm_api_key_is_never_in_repr(monkeypatch):
    monkeypatch.setenv("SCHEMA_SCOUT_LLM__API_KEY", "sk-secret")
    cfg = LlmConfig.from_settings(build_settings())
    assert cfg.api_key == "sk-secret"
    assert "sk-secret" not in repr(cfg)


def test_max_turns_is_unlimited_unless_configured(monkeypatch):
    assert AgentConfig.from_settings(build_settings()).max_turns is None
    monkeypatch.setenv("SCHEMA_SCOUT_AGENT__MAX_TURNS", "30")
    assert AgentConfig.from_settings(build_settings()).max_turns == 30


def test_null_max_turns_means_unlimited(isolated):
    f = isolated / "n.yaml"
    f.write_text("default:\n  agent:\n    max_turns:\n")
    assert AgentConfig.from_settings(build_settings([f])).max_turns is None


def test_non_positive_max_turns_rejected(monkeypatch):
    monkeypatch.setenv("SCHEMA_SCOUT_AGENT__MAX_TURNS", "0")
    with pytest.raises(ValidationError):
        build_settings()
